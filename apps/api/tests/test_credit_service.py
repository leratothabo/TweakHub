import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.auth_service import auth_service  # noqa: E402
from services.credit_service import InsufficientCreditsError, credit_service  # noqa: E402
from services.organization_service import (  # noqa: E402
    create_organization,
    get_membership,
    invite_member,
    accept_invite,
    remove_member,
)
from services.credit_service import CreditService  # noqa: E402


def _signup(db_session, email: str):
    return auth_service.signup(db_session, email, "correct horse battery", None)


def test_get_credit_cost_uses_catalog_base_cost():
    svc = CreditService()
    assert svc.get_credit_cost("pdf_merge", file_size_mb=1) == 5
    assert svc.get_credit_cost("pdf_to_word", file_size_mb=1) == 15


def test_get_credit_cost_scales_with_file_size():
    svc = CreditService()
    small = svc.get_credit_cost("pdf_compress", file_size_mb=10)
    medium = svc.get_credit_cost("pdf_compress", file_size_mb=60)   # >50MB -> x1.5
    large = svc.get_credit_cost("pdf_compress", file_size_mb=150)   # >100MB -> x2

    assert small == 8
    assert medium == 12
    assert large == 16


def test_get_credit_cost_unknown_tool_falls_back_to_default():
    svc = CreditService()
    assert svc.get_credit_cost("not_a_real_tool", file_size_mb=1) == 10


# -- Shared org credit pool (services/organization_service.py) --------------


def test_spend_credits_debits_the_users_own_balance_when_no_org(db_session):
    user = _signup(db_session, "solo-spender@example.com")
    starting = user.credit_balance
    credit_service.spend_credits(db_session, user, "pdf_merge", file_size_mb=1)
    assert user.credit_balance == starting - 5
    assert credit_service.get_effective_balance(db_session, user) == starting - 5


def test_spend_credits_debits_the_org_pool_for_a_member(db_session):
    owner = _signup(db_session, "org-spend-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    org.credit_balance = 100
    db_session.add(org)
    db_session.commit()

    owners_personal_balance = owner.credit_balance
    tx = credit_service.spend_credits(db_session, owner, "pdf_merge", file_size_mb=1)

    assert tx.organization_id == org.id
    db_session.refresh(org)
    assert org.credit_balance == 95
    assert owner.credit_balance == owners_personal_balance  # untouched — the org paid, not the person
    assert credit_service.get_effective_balance(db_session, owner) == 95


def test_spend_credits_from_org_pool_is_shared_across_members(db_session):
    owner = _signup(db_session, "org-shared-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    org.credit_balance = 100
    db_session.add(org)
    db_session.commit()

    member_user = _signup(db_session, "org-shared-member@example.com")
    invited = invite_member(db_session, org, get_membership(db_session, owner), member_user.email)
    accept_invite(db_session, invited.invite_token, member_user)

    credit_service.spend_credits(db_session, owner, "pdf_merge", file_size_mb=1)   # -5
    credit_service.spend_credits(db_session, member_user, "pdf_merge", file_size_mb=1)  # -5

    db_session.refresh(org)
    assert org.credit_balance == 90
    assert credit_service.get_effective_balance(db_session, member_user) == 90


def test_spend_credits_raises_when_org_pool_is_insufficient(db_session):
    owner = _signup(db_session, "org-broke-owner@example.com")
    create_organization(db_session, owner, "Acme Co")  # credit_balance starts at 0
    with pytest.raises(InsufficientCreditsError):
        credit_service.spend_credits(db_session, owner, "pdf_merge", file_size_mb=1)


def test_refund_credits_returns_to_the_org_pool_for_a_member(db_session):
    owner = _signup(db_session, "org-refund-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    org.credit_balance = 100
    db_session.add(org)
    db_session.commit()

    credit_service.spend_credits(db_session, owner, "pdf_merge", file_size_mb=1)
    db_session.refresh(org)
    assert org.credit_balance == 95

    tx = credit_service.refund_credits(db_session, owner, "pdf_merge", amount=5, note="failed job")
    assert tx.organization_id == org.id
    db_session.refresh(org)
    assert org.credit_balance == 100


def test_refund_follows_the_original_transaction_not_the_users_current_org(db_session):
    """Regression test for a real bug: refund_credits() used to
    re-derive _billing_target(user) at refund time instead of following
    the pool spend_credits() actually charged. An async job can sit
    queued for minutes; if the user's org membership changes in that
    window (removed here, but joining a *different* org has the same
    failure mode) and the job then fails, the old code refunded whatever
    the user belongs to *now* — draining the org that was actually
    charged and handing a free refund to the wrong place. Passing
    original_transaction (both real call sites — routes/tools.py and
    job_worker.py's _fail_job — have it via
    ProcessingJob.credit_transaction_id) is what fixes this."""
    owner = _signup(db_session, "org-refund-race-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    org.credit_balance = 100
    db_session.add(org)
    db_session.commit()

    member_user = _signup(db_session, "org-refund-race-member@example.com")
    invited = invite_member(db_session, org, get_membership(db_session, owner), member_user.email)
    accept_invite(db_session, invited.invite_token, member_user)

    # The org is charged for the member's tool run (this is what a job's
    # ProcessingJob.credit_transaction_id would point at).
    tx = credit_service.spend_credits(db_session, member_user, "pdf_merge", file_size_mb=1)
    assert tx.organization_id == org.id
    db_session.refresh(org)
    assert org.credit_balance == 95

    # The member leaves the org (or is removed) before the job's refund
    # happens — e.g. an async job that was still queued.
    remove_member(db_session, org, get_membership(db_session, owner), get_membership(db_session, member_user).id)
    assert get_membership(db_session, member_user) is None  # confirmed: no org anymore

    member_personal_balance_before = member_user.credit_balance
    credit_service.refund_credits(
        db_session, member_user, "pdf_merge", amount=5, note="failed job", original_transaction=tx,
    )

    db_session.refresh(org)
    assert org.credit_balance == 100  # the org that actually paid gets its credits back
    assert member_user.credit_balance == member_personal_balance_before  # not the ex-member personally


def test_refund_without_original_transaction_falls_back_to_current_billing_target(db_session):
    """Callers that don't have the original transaction (none exist in
    this codebase today, but the parameter is optional) get the old
    best-effort behavior rather than an error."""
    owner = _signup(db_session, "org-refund-fallback-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    org.credit_balance = 100
    db_session.add(org)
    db_session.commit()

    credit_service.spend_credits(db_session, owner, "pdf_merge", file_size_mb=1)
    db_session.refresh(org)
    assert org.credit_balance == 95

    tx = credit_service.refund_credits(db_session, owner, "pdf_merge", amount=5, note="failed job")
    assert tx.organization_id == org.id
    db_session.refresh(org)
    assert org.credit_balance == 100


def test_grant_purchased_credits_second_call_for_same_attempt_raises_not_double_grants(db_session):
    """Regression test for the atomic-guard fix: the previous plain
    `if attempt.credits_granted: raise` was a check-then-act a concurrent
    caller could slip past (see routes/payments.py's docstring — DPO's
    browser redirect and its server-to-server webhook are both expected
    to reach the same endpoint for the same payment). This test can't
    reproduce true DB-level concurrency against SQLite, but it does
    confirm the guard itself: calling grant_purchased_credits twice for
    the same attempt grants credits exactly once and the second call
    raises rather than crediting again."""
    from models import PaymentAttempt, PaymentMethod, PaymentStatus

    user = _signup(db_session, "double-grant@example.com")
    # Built directly rather than via payment_service.create_payment_attempt():
    # that method calls out to DPO's real HTTP API (see
    # payment_service.initiate_dpo_payment), which needs DPO_COMPANY_TOKEN
    # configured and live network access — neither of which this unit test
    # should depend on. grant_purchased_credits() only reads
    # id/credits/package_key/credits_granted off the row, so constructing
    # it directly exercises the same guard without the DPO round trip.
    attempt = PaymentAttempt(
        user_id=user.id,
        package_key="starter",
        amount_usd=2.99,
        credits=100,
        method=PaymentMethod.CARD,
        status=PaymentStatus.PENDING,
    )
    db_session.add(attempt)
    db_session.commit()

    before = user.credit_balance
    credit_service.grant_purchased_credits(db_session, user, attempt)
    assert user.credit_balance == before + 100

    with pytest.raises(ValueError):
        credit_service.grant_purchased_credits(db_session, user, attempt)
    db_session.refresh(user)
    assert user.credit_balance == before + 100  # not double-credited


def test_grant_bonus_credits_always_lands_on_the_individual_user(db_session):
    owner = _signup(db_session, "org-bonus-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    org.credit_balance = 100
    db_session.add(org)
    db_session.commit()

    before = owner.credit_balance
    tx = credit_service.grant_bonus_credits(db_session, owner, 25, note="test bonus")
    assert tx.organization_id is None
    assert owner.credit_balance == before + 25
    db_session.refresh(org)
    assert org.credit_balance == 100  # the org pool is untouched by a personal bonus
