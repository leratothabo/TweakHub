"""
Tests for the direct bank-transfer payment path: services/payment_service.
py's create_bank_transfer_attempt()/generate_bank_transfer_invoice_pdf(),
credit_service.initiate_purchase()'s BANK_TRANSFER branch, and the
routes/payments.py + routes/admin.py HTTP endpoints built on top of them.

Unlike the DPO-routed methods (test_credit_service.py doesn't cover those
either — they need a real DPO sandbox), this path needs no external
service at all, so it's tested end-to-end including the admin-confirm ->
credits-granted flow.
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import PaymentMethod, PaymentStatus  # noqa: E402
from services.auth_service import auth_service  # noqa: E402
from services.credit_service import credit_service  # noqa: E402
from services.payment_service import payment_service  # noqa: E402


def _signup(db_session, email: str):
    return auth_service.signup(db_session, email, "correct horse battery", None)


# -- service-level: reference generation + attempt creation -----------------


def test_create_bank_transfer_attempt_generates_tweakhub_reference(db_session):
    user = _signup(db_session, "bank-ref@example.com")
    attempt = payment_service.create_bank_transfer_attempt(
        db=db_session, user=user, package_key="starter", amount_usd=2.99, credits=100
    )
    assert attempt.method == PaymentMethod.BANK_TRANSFER
    assert attempt.status == PaymentStatus.PENDING
    assert attempt.dpo_transaction_token is None
    assert attempt.bank_reference is not None
    assert attempt.bank_reference.startswith("TweakHub")
    assert attempt.bank_reference[len("TweakHub"):].isdigit()


def test_bank_transfer_references_are_sequential_and_unique(db_session):
    user = _signup(db_session, "bank-ref-seq@example.com")
    first = payment_service.create_bank_transfer_attempt(
        db=db_session, user=user, package_key="starter", amount_usd=2.99, credits=100
    )
    second = payment_service.create_bank_transfer_attempt(
        db=db_session, user=user, package_key="starter", amount_usd=2.99, credits=100
    )
    assert first.bank_reference != second.bank_reference
    first_n = int(first.bank_reference[len("TweakHub"):])
    second_n = int(second.bank_reference[len("TweakHub"):])
    assert second_n == first_n + 1


def test_bank_transfer_invoice_pdf_contains_reference_and_bank_details(db_session):
    from pypdf import PdfReader

    user = _signup(db_session, "bank-invoice@example.com")
    attempt = payment_service.create_bank_transfer_attempt(
        db=db_session, user=user, package_key="starter", amount_usd=2.99, credits=100
    )
    pdf_bytes = payment_service.generate_bank_transfer_invoice_pdf(attempt, user)
    assert pdf_bytes[:4] == b"%PDF"

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert attempt.bank_reference in text
    assert "Standard Bank" in text
    assert "10275365741" in text
    assert user.email in text


# -- credit_service.initiate_purchase branch ---------------------------------


def test_initiate_purchase_bank_transfer_skips_dpo_and_returns_reference(db_session):
    user = _signup(db_session, "purchase-bank@example.com")
    result = credit_service.initiate_purchase(db_session, user, "starter", PaymentMethod.BANK_TRANSFER)

    assert result["payment_method"] == "bank_transfer"
    assert result["bank_reference"].startswith("TweakHub")
    assert result["bank_details"]["account_number"] == "10275365741"
    assert result["bank_details"]["bank_name"] == "Standard Bank"
    assert "payment_url" not in result


# -- HTTP: routes/credits.py + routes/payments.py + routes/admin.py --------


def _signup_and_login(client, email: str) -> str:
    client.post("/api/auth/signup", json={"email": email, "password": "correct horse battery"})
    res = client.post("/api/auth/login", json={"email": email, "password": "correct horse battery"})
    return res.json()["access_token"]


def test_purchase_route_bank_transfer_returns_instructions(client):
    token = _signup_and_login(client, "route-bank@example.com")
    res = client.post(
        "/api/credits/purchase",
        json={"package_key": "starter", "method": "bank_transfer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["payment_method"] == "bank_transfer"
    assert body["bank_reference"].startswith("TweakHub")


def test_bank_transfer_invoice_route_returns_pdf_for_owner(client):
    token = _signup_and_login(client, "route-invoice@example.com")
    purchase = client.post(
        "/api/credits/purchase",
        json={"package_key": "starter", "method": "bank_transfer"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    res = client.get(
        f"/api/payments/bank-transfer/{purchase['payment_attempt_id']}/invoice",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"


def test_bank_transfer_invoice_route_404s_for_a_different_user(client):
    token_a = _signup_and_login(client, "invoice-owner@example.com")
    token_b = _signup_and_login(client, "invoice-stranger@example.com")
    purchase = client.post(
        "/api/credits/purchase",
        json={"package_key": "starter", "method": "bank_transfer"},
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()

    res = client.get(
        f"/api/payments/bank-transfer/{purchase['payment_attempt_id']}/invoice",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404


def test_admin_routes_reject_non_admin_users(client):
    token = _signup_and_login(client, "not-admin@example.com")
    res = client.get("/api/admin/bank-transfers/pending", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_admin_confirm_grants_credits_exactly_once(client, db_session):
    from models import User

    customer_token = _signup_and_login(client, "confirm-customer@example.com")
    purchase = client.post(
        "/api/credits/purchase",
        json={"package_key": "starter", "method": "bank_transfer"},
        headers={"Authorization": f"Bearer {customer_token}"},
    ).json()

    admin_token = _signup_and_login(client, "confirm-admin@example.com")
    admin_user = db_session.query(User).filter(User.email == "confirm-admin@example.com").first()
    admin_user.is_admin = True
    db_session.add(admin_user)
    db_session.commit()

    pending = client.get(
        "/api/admin/bank-transfers/pending", headers={"Authorization": f"Bearer {admin_token}"}
    ).json()
    assert any(row["id"] == purchase["payment_attempt_id"] for row in pending["pending"])

    customer = db_session.query(User).filter(User.email == "confirm-customer@example.com").first()
    balance_before = customer.credit_balance

    attempt_id = purchase["payment_attempt_id"]
    res = client.post(
        f"/api/admin/bank-transfers/{attempt_id}/confirm",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "succeeded", "credits_granted": True}

    db_session.refresh(customer)
    assert customer.credit_balance == balance_before + purchase["credits"]

    # Confirming again is a no-op, not a double grant.
    res2 = client.post(
        f"/api/admin/bank-transfers/{attempt_id}/confirm",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res2.status_code == 200
    db_session.refresh(customer)
    assert customer.credit_balance == balance_before + purchase["credits"]


def test_admin_confirm_404s_for_unknown_attempt(client, db_session):
    from models import User

    admin_token = _signup_and_login(client, "confirm-admin-2@example.com")
    admin_user = db_session.query(User).filter(User.email == "confirm-admin-2@example.com").first()
    admin_user.is_admin = True
    db_session.add(admin_user)
    db_session.commit()

    res = client.post(
        "/api/admin/bank-transfers/does-not-exist/confirm",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 404
