"""
Tests for services/bank_reconciliation.py and the /api/admin/bank-statements/
reconcile/* routes: statement CSV parsing (with and without a header row,
messy hand-typed references, ZAR formatting), match classification against
pending bank-transfer attempts, and the full upload -> preview -> batch
confirm -> credits-granted flow, including that a re-uploaded statement
can't double-credit anyone.
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import PaymentStatus  # noqa: E402
from services import bank_reconciliation  # noqa: E402
from services.auth_service import auth_service  # noqa: E402
from services.payment_service import payment_service  # noqa: E402


def _attempt(db_session, email: str, package_key: str = "starter", credits: int = 100):
    user = auth_service.signup(db_session, email, "correct horse battery", None)
    return payment_service.create_bank_transfer_attempt(
        db=db_session, user=user, package_key=package_key, amount_usd=2.99, credits=credits
    )


# -- parsing -----------------------------------------------------------------


def test_parse_with_header_uses_amount_column():
    csv_bytes = (
        b"Date,Description,Reference,Amount,Balance\n"
        b"2026/10/27,IB PAYMENT FROM,TweakHub000042,185.00,10185.00\n"
        b"2026/10/27,MONTHLY FEE,,-65.00,10120.00\n"
    )
    lines = bank_reconciliation.parse_statement(csv_bytes)
    assert len(lines) == 1
    assert lines[0].reference == "TweakHub000042"
    assert lines[0].amount_zar == Decimal("185.00")


def test_parse_without_header_skips_dates_and_finds_amount():
    csv_bytes = b"HIST,20261027,,1850.00,CREDIT TRANSFER,tweakhub 000007,\n"
    lines = bank_reconciliation.parse_statement(csv_bytes)
    assert lines[0].reference == "TweakHub000007"
    assert lines[0].amount_zar == Decimal("1850.00")


def test_parse_tolerates_messy_references_and_rand_formatting():
    csv_bytes = (
        b"Date;Details;Credit\n"
        b"27 Oct 2026;PMT TWEAK HUB-000101 THANKS;R 1 850,00\n"
    )
    # Decimal comma + space thousands — must not be misread as R185,000.
    lines = bank_reconciliation.parse_statement(csv_bytes)
    assert lines[0].reference == "TweakHub000101"
    assert lines[0].amount_zar == Decimal("1850.00")


def test_parse_money_formats():
    p = bank_reconciliation._parse_money
    assert p("185,50") == Decimal("185.50")
    assert p("1,850") == Decimal("1850")
    assert p("1.850,00") == Decimal("1850.00")
    assert p("R1 850.00") == Decimal("1850.00")
    assert p("-65.00") == Decimal("-65.00")
    assert p("not money") is None


def test_parse_handles_thousands_separator():
    csv_bytes = b"Date,Description,Amount\n2026-10-27,TweakHub000005,\"1,850.00\"\n"
    lines = bank_reconciliation.parse_statement(csv_bytes)
    assert lines[0].amount_zar == Decimal("1850.00")


def test_parse_empty_file_raises():
    try:
        bank_reconciliation.parse_statement(b"   ")
    except bank_reconciliation.StatementParseError:
        return
    raise AssertionError("expected StatementParseError")


# -- preview classification --------------------------------------------------


def test_preview_classifies_match_underpaid_and_unknown(db_session):
    paid = _attempt(db_session, "recon-paid@example.com")  # starter = R55
    short = _attempt(db_session, "recon-short@example.com")
    csv_bytes = (
        "Date,Description,Amount\n"
        f"2026-10-27,{paid.bank_reference},55.00\n"
        f"2026-10-27,{short.bank_reference},40.00\n"
        "2026-10-27,TweakHub999999,55.00\n"
        "2026-10-27,SOMEONE ELSE,100.00\n"
    ).encode()

    result = bank_reconciliation.preview_statement(db_session, csv_bytes)
    by_ref = {r["reference"]: r for r in result["rows"]}

    assert by_ref[paid.bank_reference]["status"] == "match"
    assert by_ref[paid.bank_reference]["expected_zar"] == 55.0
    assert by_ref[paid.bank_reference]["attempt_id"] == paid.id
    assert by_ref[short.bank_reference]["status"] == "underpaid"
    assert by_ref["TweakHub999999"]["status"] == "unknown_reference"
    assert result["summary"]["matches"] == 1
    assert result["summary"]["lines_with_reference"] == 3

    # Preview is read-only.
    db_session.refresh(paid)
    assert paid.status == PaymentStatus.PENDING
    assert paid.credits_granted is False


def test_preview_sums_split_payments_for_one_reference(db_session):
    attempt = _attempt(db_session, "recon-split@example.com")
    csv_bytes = (
        "Date,Description,Amount\n"
        f"2026-10-27,{attempt.bank_reference},30.00\n"
        f"2026-10-28,{attempt.bank_reference},25.00\n"
    ).encode()
    rows = bank_reconciliation.preview_statement(db_session, csv_bytes)["rows"]
    assert len(rows) == 1
    assert rows[0]["paid_zar"] == 55.0
    assert rows[0]["status"] == "match"


def test_overpayment_still_matches(db_session):
    attempt = _attempt(db_session, "recon-over@example.com")
    csv_bytes = f"Date,Description,Amount\n2026-10-27,{attempt.bank_reference},60.00\n".encode()
    rows = bank_reconciliation.preview_statement(db_session, csv_bytes)["rows"]
    assert rows[0]["status"] == "match"


# -- HTTP: upload -> preview -> confirm --------------------------------------


def _signup_and_login(client, email: str) -> str:
    client.post("/api/auth/signup", json={"email": email, "password": "correct horse battery"})
    return client.post("/api/auth/login", json={"email": email, "password": "correct horse battery"}).json()[
        "access_token"
    ]


def _make_admin(client, db_session, email: str) -> str:
    from models import User

    token = _signup_and_login(client, email)
    user = db_session.query(User).filter(User.email == email).first()
    user.is_admin = True
    db_session.add(user)
    db_session.commit()
    return token


def test_reconcile_routes_reject_non_admin(client):
    token = _signup_and_login(client, "recon-nonadmin@example.com")
    res = client.post(
        "/api/admin/bank-statements/preview",
        files={"statement": ("s.csv", b"Date,Amount\n", "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    res = client.post(
        "/api/admin/bank-statements/confirm",
        json={"attempt_ids": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_upload_preview_confirm_grants_credits_once(client, db_session):
    from models import User

    customer_token = _signup_and_login(client, "recon-customer@example.com")
    purchase = client.post(
        "/api/credits/purchase",
        json={"package_key": "popular", "method": "bank_transfer"},
        headers={"Authorization": f"Bearer {customer_token}"},
    ).json()
    admin_token = _make_admin(client, db_session, "recon-admin@example.com")
    auth = {"Authorization": f"Bearer {admin_token}"}

    statement = f"Date,Description,Amount\n2026-10-27,PAYMENT {purchase['bank_reference']},185.00\n".encode()
    preview = client.post(
        "/api/admin/bank-statements/preview",
        files={"statement": ("statement.csv", statement, "text/csv")},
        headers=auth,
    )
    assert preview.status_code == 200, preview.text
    row = preview.json()["rows"][0]
    assert row["status"] == "match"
    assert row["attempt_id"] == purchase["payment_attempt_id"]

    customer = db_session.query(User).filter(User.email == "recon-customer@example.com").first()
    before = customer.credit_balance

    res = client.post(
        "/api/admin/bank-statements/confirm",
        json={"attempt_ids": [row["attempt_id"], "no-such-id"]},
        headers=auth,
    )
    assert res.status_code == 200
    assert res.json()["confirmed"] == [row["attempt_id"]]
    assert res.json()["skipped"][0]["attempt_id"] == "no-such-id"
    db_session.refresh(customer)
    assert customer.credit_balance == before + purchase["credits"]

    # Same statement uploaded again: shows as already confirmed, and a
    # repeat confirm doesn't double-credit.
    again = client.post(
        "/api/admin/bank-statements/preview",
        files={"statement": ("statement.csv", statement, "text/csv")},
        headers=auth,
    ).json()
    assert again["rows"][0]["status"] == "already_confirmed"
    client.post(
        "/api/admin/bank-statements/confirm", json={"attempt_ids": [row["attempt_id"]]}, headers=auth
    )
    db_session.refresh(customer)
    assert customer.credit_balance == before + purchase["credits"]


def test_preview_rejects_empty_file(client, db_session):
    admin_token = _make_admin(client, db_session, "recon-admin-empty@example.com")
    res = client.post(
        "/api/admin/bank-statements/preview",
        files={"statement": ("s.csv", b"", "text/csv")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 400
