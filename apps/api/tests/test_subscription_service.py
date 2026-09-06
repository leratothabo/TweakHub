"""
Tests for the recurring-subscription feature: services/
subscription_service.py's initiate/cancel/webhook-handling logic, and the
signature-verification gate on POST /api/payments/paystack/webhook
(routes/payments.py). Like test_bank_transfer.py, this needs no real
external service -- payment_service.initialize_paystack_transaction/
disable_paystack_subscription are monkeypatched rather than hitting a real
Paystack sandbox, and the webhook signature is computed the same way
payment_service.verify_paystack_webhook_signature checks it (HMAC-SHA512
of the raw body, keyed by PAYSTACK_SECRET_KEY).
"""
import hashlib
import hmac
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import PlanTier, SubscriptionStatus  # noqa: E402
from services.auth_service import auth_service  # noqa: E402
from services.payment_service import payment_service  # noqa: E402
from services.subscription_service import (  # noqa: E402
    SubscriptionServiceError,
    cancel_subscription,
    get_subscription_for_user,
    handle_paystack_event,
    initiate_subscription,
)


def _signup(db_session, email: str):
    return auth_service.signup(db_session, email, "correct horse battery", None)


def _fake_initialize_paystack_transaction(monkeypatch, authorization_url="https://paystack.test/pay/abc123"):
    """Stands in for payment_service.initialize_paystack_transaction so
    initiate_subscription() never makes a real HTTP call. Returns the same
    shape the real method does, echoing back whatever `reference` it was
    given (subscription_service passes the new Subscription's own id)."""

    def _fake(email, amount_kobo, reference=None, callback_url=None, plan=None):
        assert plan  # subscription flow must always pass a Paystack plan code
        return {"authorization_url": authorization_url, "access_code": "code_123", "reference": reference}

    monkeypatch.setattr(payment_service, "initialize_paystack_transaction", _fake)


def _configure_plan_codes(override_settings):
    override_settings(
        paystack_secret_key="sk_test_dummysecret",
        paystack_plan_code_pro="plan_pro_123",
        paystack_plan_code_business="plan_business_456",
    )


# -- initiate_subscription ----------------------------------------------


def test_initiate_subscription_creates_pending_row_and_returns_url(db_session, monkeypatch, override_settings):
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)

    user = _signup(db_session, "subscribe-pending@example.com")
    subscription, authorization_url = initiate_subscription(db_session, user, "pro")

    assert authorization_url == "https://paystack.test/pay/abc123"
    assert subscription.status == SubscriptionStatus.PENDING
    assert subscription.plan_key == "pro"
    assert subscription.paystack_plan_code == "plan_pro_123"
    assert subscription.paystack_subscription_code is None
    # Not upgraded yet -- only the webhook does that.
    assert user.plan_tier == PlanTier.FREE


def test_initiate_subscription_rejects_unknown_plan(db_session, monkeypatch, override_settings):
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "subscribe-badplan@example.com")

    try:
        initiate_subscription(db_session, user, "enterprise-deluxe")
        assert False, "expected SubscriptionServiceError"
    except SubscriptionServiceError:
        pass


def test_initiate_subscription_rejects_a_second_active_subscription(db_session, monkeypatch, override_settings):
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "subscribe-twice@example.com")

    initiate_subscription(db_session, user, "pro")
    try:
        initiate_subscription(db_session, user, "business")
        assert False, "expected SubscriptionServiceError"
    except SubscriptionServiceError:
        pass


def test_initiate_subscription_requires_plan_code_configured(db_session, monkeypatch, override_settings):
    override_settings(paystack_secret_key="sk_test_dummysecret")  # no plan codes set
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "subscribe-noplancode@example.com")

    try:
        initiate_subscription(db_session, user, "pro")
        assert False, "expected SubscriptionServiceError"
    except SubscriptionServiceError:
        pass


# -- subscription.create webhook -----------------------------------------


def _subscription_create_event(subscription_id: str, email: str, subscription_code="SUB_abc123"):
    return {
        "event": "subscription.create",
        "data": {
            "reference": subscription_id,
            "subscription_code": subscription_code,
            "email_token": "tok_abc123",
            "next_payment_date": "2026-10-05T00:00:00.000Z",
            "customer": {"email": email, "customer_code": "CUS_xyz"},
        },
    }


def test_subscription_create_webhook_activates_upgrades_and_grants_credits_once(
    db_session, monkeypatch, override_settings
):
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "webhook-create@example.com")
    subscription, _ = initiate_subscription(db_session, user, "pro")
    starting_balance = user.credit_balance

    event = _subscription_create_event(subscription.id, user.email)
    handle_paystack_event(db_session, event)

    db_session.refresh(user)
    db_session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.paystack_subscription_code == "SUB_abc123"
    assert subscription.paystack_email_token == "tok_abc123"
    assert subscription.current_period_end is not None
    assert user.plan_tier == PlanTier.PRO
    assert user.credit_balance == starting_balance + 1000  # SUBSCRIPTION_PLANS["pro"]["monthly_credits"]

    # Redelivered webhook (Paystack retries on timeout/non-2xx) must not
    # double-activate, double-upgrade, or double-grant.
    handle_paystack_event(db_session, event)
    db_session.refresh(user)
    db_session.refresh(subscription)
    assert user.credit_balance == starting_balance + 1000
    assert subscription.status == SubscriptionStatus.ACTIVE


def test_subscription_create_webhook_matches_by_customer_email_when_reference_unknown(
    db_session, monkeypatch, override_settings
):
    """Paystack's subscription.create payload doesn't always echo our own
    reference back -- the fallback match is by customer email + most
    recent PENDING row (see subscription_service._find_subscription_for_
    create_event's docstring)."""
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "webhook-email-match@example.com")
    subscription, _ = initiate_subscription(db_session, user, "business")

    event = {
        "event": "subscription.create",
        "data": {
            # No "reference" field at all -- forces the email fallback.
            "subscription_code": "SUB_email_fallback",
            "email_token": "tok_fallback",
            "next_payment_date": "2026-10-05T00:00:00.000Z",
            "customer": {"email": user.email, "customer_code": "CUS_fallback"},
        },
    }
    handle_paystack_event(db_session, event)

    db_session.refresh(subscription)
    db_session.refresh(user)
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.paystack_subscription_code == "SUB_email_fallback"
    assert user.plan_tier == PlanTier.BUSINESS


# -- charge.success renewal -----------------------------------------------


def test_charge_success_renewal_grants_credits_and_advances_period_but_not_on_replay(
    db_session, monkeypatch, override_settings
):
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "webhook-renewal@example.com")
    subscription, _ = initiate_subscription(db_session, user, "pro")
    handle_paystack_event(db_session, _subscription_create_event(subscription.id, user.email))

    db_session.refresh(user)
    db_session.refresh(subscription)
    balance_after_first_period = user.credit_balance
    first_period_end = subscription.current_period_end

    renewal_event = {
        "event": "charge.success",
        "data": {
            "subscription": {
                "subscription_code": subscription.paystack_subscription_code,
                "next_payment_date": "2026-11-05T00:00:00.000Z",
            },
        },
    }
    handle_paystack_event(db_session, renewal_event)

    db_session.refresh(user)
    db_session.refresh(subscription)
    assert user.credit_balance == balance_after_first_period + 1000
    assert subscription.current_period_end > first_period_end

    # Replaying the exact same renewal event must not grant a second time.
    handle_paystack_event(db_session, renewal_event)
    db_session.refresh(user)
    assert user.credit_balance == balance_after_first_period + 1000


def test_charge_success_for_the_initial_charge_does_not_double_grant_the_first_period(
    db_session, monkeypatch, override_settings
):
    """Paystack fires charge.success for the very first charge too, on top
    of subscription.create -- its next_payment_date is the same period
    subscription.create already recorded/granted, so this must be a
    no-op."""
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "webhook-initial-charge@example.com")
    subscription, _ = initiate_subscription(db_session, user, "pro")
    handle_paystack_event(db_session, _subscription_create_event(subscription.id, user.email))

    db_session.refresh(user)
    balance_after_activation = user.credit_balance

    initial_charge_event = {
        "event": "charge.success",
        "data": {
            "subscription": {
                "subscription_code": subscription.paystack_subscription_code,
                "next_payment_date": "2026-10-05T00:00:00.000Z",  # same as subscription.create's
            },
        },
    }
    handle_paystack_event(db_session, initial_charge_event)

    db_session.refresh(user)
    assert user.credit_balance == balance_after_activation


# -- invoice.payment_failed / subscription.disable ------------------------


def test_invoice_payment_failed_sets_past_due(db_session, monkeypatch, override_settings):
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "webhook-past-due@example.com")
    subscription, _ = initiate_subscription(db_session, user, "pro")
    handle_paystack_event(db_session, _subscription_create_event(subscription.id, user.email))

    event = {
        "event": "invoice.payment_failed",
        "data": {"subscription": {"subscription_code": subscription.paystack_subscription_code}},
    }
    handle_paystack_event(db_session, event)

    db_session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.PAST_DUE


def test_subscription_disable_sets_cancelled(db_session, monkeypatch, override_settings):
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "webhook-disable@example.com")
    subscription, _ = initiate_subscription(db_session, user, "pro")
    handle_paystack_event(db_session, _subscription_create_event(subscription.id, user.email))

    event = {
        "event": "subscription.disable",
        "data": {"subscription_code": subscription.paystack_subscription_code},
    }
    handle_paystack_event(db_session, event)

    db_session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.CANCELLED
    assert subscription.cancel_at_period_end is True


# -- cancel_subscription ---------------------------------------------------


def test_cancel_subscription_sets_cancel_at_period_end_and_calls_paystack(
    db_session, monkeypatch, override_settings
):
    _configure_plan_codes(override_settings)
    _fake_initialize_paystack_transaction(monkeypatch)
    user = _signup(db_session, "cancel-active@example.com")
    subscription, _ = initiate_subscription(db_session, user, "pro")
    handle_paystack_event(db_session, _subscription_create_event(subscription.id, user.email))

    calls = []
    monkeypatch.setattr(
        payment_service,
        "disable_paystack_subscription",
        lambda code, token: calls.append((code, token)),
    )

    result = cancel_subscription(db_session, user)
    assert result.cancel_at_period_end is True
    assert calls == [(subscription.paystack_subscription_code, subscription.paystack_email_token)]
    # status itself waits for the subscription.disable webhook, not this call.
    db_session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.ACTIVE


def test_get_subscription_for_user_returns_none_when_none_exists(db_session):
    user = _signup(db_session, "no-subscription@example.com")
    assert get_subscription_for_user(db_session, user) is None


# -- HTTP: POST /api/payments/paystack/webhook signature gate --------------


def _sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()


def test_webhook_route_rejects_missing_signature(client, override_settings):
    override_settings(paystack_secret_key="sk_test_dummysecret")
    body = json.dumps({"event": "subscription.create", "data": {}}).encode("utf-8")
    res = client.post(
        "/api/payments/paystack/webhook",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 400


def test_webhook_route_rejects_wrong_signature(client, override_settings):
    override_settings(paystack_secret_key="sk_test_dummysecret")
    body = json.dumps({"event": "subscription.create", "data": {}}).encode("utf-8")
    res = client.post(
        "/api/payments/paystack/webhook",
        content=body,
        headers={"Content-Type": "application/json", "x-paystack-signature": "0" * 128},
    )
    assert res.status_code == 400


def test_webhook_route_accepts_correctly_signed_request_and_activates_subscription(
    client, db_session, monkeypatch, override_settings
):
    secret = "sk_test_dummysecret"
    _configure_plan_codes(override_settings)
    override_settings(paystack_secret_key=secret)
    _fake_initialize_paystack_transaction(monkeypatch)

    user = _signup(db_session, "webhook-route-ok@example.com")
    subscription, _ = initiate_subscription(db_session, user, "pro")

    event = _subscription_create_event(subscription.id, user.email)
    body = json.dumps(event).encode("utf-8")
    signature = _sign(secret, body)

    res = client.post(
        "/api/payments/paystack/webhook",
        content=body,
        headers={"Content-Type": "application/json", "x-paystack-signature": signature},
    )
    assert res.status_code == 200, res.text

    db_session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.ACTIVE
