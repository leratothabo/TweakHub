import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.auth_service import auth_service  # noqa: E402
from services.credit_service import InsufficientCreditsError, credit_service  # noqa: E402
from services.organization_service import create_organization, get_membership, invite_member, accept_invite  # noqa: E402
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
