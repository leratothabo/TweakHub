import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.auth_service import AuthError, auth_service  # noqa: E402


def test_signup_creates_unverified_user_with_bonus_credits(db_session):
    user = auth_service.signup(db_session, "new@example.com", "correct horse battery", "New User")
    assert user.is_email_verified is False
    assert user.credit_balance == 25
    assert user.email_verification_token is not None
    assert user.password_hash != "correct horse battery"  # never store plaintext


def test_signup_generates_a_unique_referral_code(db_session):
    a = auth_service.signup(db_session, "refcode-a@example.com", "correct horse battery", None)
    b = auth_service.signup(db_session, "refcode-b@example.com", "correct horse battery", None)
    assert a.referral_code is not None
    assert len(a.referral_code) == 8
    assert a.referral_code != b.referral_code
    assert a.referred_by_user_id is None  # nobody referred them


def test_signup_rejects_duplicate_email(db_session):
    auth_service.signup(db_session, "dup@example.com", "correct horse battery", None)
    with pytest.raises(AuthError, match="already exists"):
        auth_service.signup(db_session, "dup@example.com", "another password", None)


def test_signup_rejects_short_password(db_session):
    with pytest.raises(AuthError, match="8 characters"):
        auth_service.signup(db_session, "short@example.com", "abc123", None)


def test_login_succeeds_with_correct_password_in_dev(db_session):
    auth_service.signup(db_session, "login@example.com", "correct horse battery", None)
    user = auth_service.login(db_session, "login@example.com", "correct horse battery")
    assert user.email == "login@example.com"


def test_login_rejects_wrong_password(db_session):
    auth_service.signup(db_session, "wrongpw@example.com", "correct horse battery", None)
    with pytest.raises(AuthError, match="Invalid email or password"):
        auth_service.login(db_session, "wrongpw@example.com", "totally wrong")


def test_login_rejects_unknown_email(db_session):
    with pytest.raises(AuthError, match="Invalid email or password"):
        auth_service.login(db_session, "nobody@example.com", "whatever123")


def test_verify_email_marks_user_verified_and_consumes_token(db_session):
    user = auth_service.signup(db_session, "verify@example.com", "correct horse battery", None)
    token = user.email_verification_token

    verified = auth_service.verify_email(db_session, token)
    assert verified.is_email_verified is True
    assert verified.email_verification_token is None

    with pytest.raises(AuthError, match="Invalid or expired"):
        auth_service.verify_email(db_session, token)  # token already consumed


def test_password_reset_flow(db_session):
    user = auth_service.signup(db_session, "reset@example.com", "old password 1", None)
    auth_service.request_password_reset(db_session, "reset@example.com")

    db_session.refresh(user)
    token = user.password_reset_token
    assert token is not None

    auth_service.reset_password(db_session, token, "brand new password")

    # old password no longer works, new one does
    with pytest.raises(AuthError):
        auth_service.login(db_session, "reset@example.com", "old password 1")
    logged_in = auth_service.login(db_session, "reset@example.com", "brand new password")
    assert logged_in.email == "reset@example.com"


def test_request_password_reset_for_unknown_email_does_not_raise(db_session):
    # Must not reveal whether the email is registered.
    auth_service.request_password_reset(db_session, "ghost@example.com")


def test_signup_with_valid_referral_code_links_the_referrer(db_session):
    referrer = auth_service.signup(db_session, "referrer@example.com", "correct horse battery", None)
    invitee = auth_service.signup(
        db_session, "invitee@example.com", "correct horse battery", None,
        referral_code=referrer.referral_code,
    )
    assert invitee.referred_by_user_id == referrer.id


def test_signup_with_referral_code_is_case_insensitive(db_session):
    referrer = auth_service.signup(db_session, "referrer2@example.com", "correct horse battery", None)
    invitee = auth_service.signup(
        db_session, "invitee2@example.com", "correct horse battery", None,
        referral_code=referrer.referral_code.lower(),
    )
    assert invitee.referred_by_user_id == referrer.id


def test_signup_with_unknown_referral_code_is_silently_ignored(db_session):
    # A stale/mistyped ?ref= link shouldn't block account creation.
    user = auth_service.signup(
        db_session, "no-ref@example.com", "correct horse battery", None,
        referral_code="NOTAREALCODE",
    )
    assert user.referred_by_user_id is None
    assert user.is_email_verified is False  # signup itself still succeeded


def test_referral_bonus_granted_to_both_sides_on_invitee_email_verification(db_session):
    referrer = auth_service.signup(db_session, "bonus-referrer@example.com", "correct horse battery", None)
    referrer_balance_before = referrer.credit_balance

    invitee = auth_service.signup(
        db_session, "bonus-invitee@example.com", "correct horse battery", None,
        referral_code=referrer.referral_code,
    )
    invitee_balance_before_verify = invitee.credit_balance
    token = invitee.email_verification_token

    auth_service.verify_email(db_session, token)

    db_session.refresh(invitee)
    db_session.refresh(referrer)
    assert invitee.credit_balance == invitee_balance_before_verify + 25
    assert referrer.credit_balance == referrer_balance_before + 50

    # Audit trail: a BONUS transaction exists for each side.
    from models import CreditTransaction, CreditTransactionType

    invitee_bonus = (
        db_session.query(CreditTransaction)
        .filter(CreditTransaction.user_id == invitee.id, CreditTransaction.type == CreditTransactionType.BONUS)
        .first()
    )
    referrer_bonus = (
        db_session.query(CreditTransaction)
        .filter(CreditTransaction.user_id == referrer.id, CreditTransaction.type == CreditTransactionType.BONUS)
        .first()
    )
    assert invitee_bonus is not None
    assert referrer_bonus is not None


def test_referral_bonus_not_granted_when_no_referrer(db_session):
    user = auth_service.signup(db_session, "solo-signup@example.com", "correct horse battery", None)
    balance_before = user.credit_balance
    token = user.email_verification_token

    auth_service.verify_email(db_session, token)

    db_session.refresh(user)
    assert user.credit_balance == balance_before  # no referral, no bonus


def test_referral_bonus_cannot_be_farmed_by_reverifying(db_session):
    # verify_email() can only succeed once per user (token cleared on
    # first use) — this is what actually prevents double-granting, not a
    # separate "already granted" flag. Confirm the second call still
    # raises and the invitee's balance doesn't move again.
    referrer = auth_service.signup(db_session, "farm-referrer@example.com", "correct horse battery", None)
    invitee = auth_service.signup(
        db_session, "farm-invitee@example.com", "correct horse battery", None,
        referral_code=referrer.referral_code,
    )
    token = invitee.email_verification_token
    auth_service.verify_email(db_session, token)
    db_session.refresh(invitee)
    balance_after_first_verify = invitee.credit_balance

    with pytest.raises(AuthError):
        auth_service.verify_email(db_session, token)

    db_session.refresh(invitee)
    assert invitee.credit_balance == balance_after_first_verify
