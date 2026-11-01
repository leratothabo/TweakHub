"""
app/services/bank_reconciliation.py

Matches a bank-statement CSV export (Standard Bank online banking, or any
bank's CSV) against PENDING bank-transfer PaymentAttempts, so an admin can
confirm a day's EFTs in one step instead of one "Mark received" click per
row after eyeballing the statement.

No bank API and no third party: the admin downloads the statement CSV from
their own online banking and uploads it to /admin. This module only
*proposes* matches (preview_statement) — nothing is credited until the
admin reviews the preview and confirms the rows they agree with
(routes/admin.py), through the same idempotent confirm path as the manual
button.

Parsing is deliberately tolerant, because bank CSV layouts vary (and
change) and there's no published, stable Standard Bank schema to code
against:

- The reference is found by scanning *every* cell in a row for
  TweakHub + 6 digits (case-insensitive, tolerating a space or dash between
  the word and the number — people retype references by hand), so it
  doesn't matter whether it lands in a "Description", "Reference" or
  "Details" column.
- The amount comes from a header column named like amount/credit/deposit
  when a header row exists; otherwise the first positive money-looking
  cell that isn't the reference or a date. The admin sees the parsed
  amount for every row in the preview, so a bad guess is visible before
  anything is confirmed.

Amount check: bank transfers land in a ZAR account, so the expected amount
is the package's price_zar (credit_service.CREDIT_PACKAGES), not the
attempt's amount_usd. Paying the expected amount or more is a match;
paying less is flagged "underpaid" and not pre-selected.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from models import PaymentAttempt, PaymentMethod, PaymentStatus, User

REFERENCE_RE = re.compile(r"tweak\s*hub[\s\-_]*(\d{6})", re.IGNORECASE)
_MONEY_RE = re.compile(r"^-?\s*(?:R|ZAR)?\s*-?[\d\s.,]*\d\s*(?:CR)?$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{8}$|^\d{4}[-/]\d{2}[-/]\d{2}|^\d{1,2}[-/ ]\w{2,9}[-/ ]\d{2,4}$")
_AMOUNT_HEADERS = ("amount", "credit", "deposit", "money in", "value")
_TOLERANCE = Decimal("0.01")

MATCH = "match"
UNDERPAID = "underpaid"
ALREADY_CONFIRMED = "already_confirmed"
UNKNOWN_REFERENCE = "unknown_reference"
NOT_PENDING = "not_pending"


class StatementParseError(ValueError):
    pass


@dataclass
class StatementLine:
    reference: str
    amount_zar: Decimal | None
    raw: str


@dataclass
class ReconciliationRow:
    reference: str
    status: str
    paid_zar: float | None
    expected_zar: float | None = None
    attempt_id: str | None = None
    user_email: str | None = None
    package_key: str | None = None
    credits: int | None = None
    statement_lines: list[str] = field(default_factory=list)


def _parse_money(cell: str) -> Decimal | None:
    text = cell.strip()
    if not text or not _MONEY_RE.match(text):
        return None
    negative = "-" in text
    digits = re.sub(r"[^\d.,]", "", text)
    # South African exports use both "1,850.00" and "1 850,00". Whichever
    # of "." / "," comes last is the decimal mark when both appear; a lone
    # comma is a decimal mark only when followed by exactly 1-2 digits
    # ("185,50"), otherwise it's a thousands separator ("1,850").
    if "," in digits and "." in digits:
        if digits.rfind(",") > digits.rfind("."):
            digits = digits.replace(".", "").replace(",", ".")
        else:
            digits = digits.replace(",", "")
    elif "," in digits:
        if re.search(r",\d{1,2}$", digits) and digits.count(",") == 1:
            digits = digits.replace(",", ".")
        else:
            digits = digits.replace(",", "")
    cleaned = digits
    if not cleaned or cleaned.count(".") > 1:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -value if negative else value


def _normalise_reference(match: re.Match) -> str:
    return f"TweakHub{match.group(1)}"


def _find_amount_column(header: list[str]) -> int | None:
    lowered = [h.strip().lower() for h in header]
    for wanted in _AMOUNT_HEADERS:
        for idx, name in enumerate(lowered):
            if wanted in name and "balance" not in name and "debit" not in name:
                return idx
    return None


def _looks_like_header(row: list[str]) -> bool:
    cells = [c.strip() for c in row if c.strip()]
    if not cells:
        return False
    no_money = all(_parse_money(c) is None for c in cells)
    return no_money and any(any(w in c.lower() for w in _AMOUNT_HEADERS) for c in cells)


def parse_statement(raw: bytes) -> list[StatementLine]:
    """Extracts every line that carries a TweakHub reference. Lines without
    one (bank fees, other income) are ignored — they aren't ours to match."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    if not text.strip():
        raise StatementParseError("The statement file is empty.")

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))

    amount_col: int | None = None
    lines: list[StatementLine] = []
    for row in rows:
        if amount_col is None and _looks_like_header(row):
            amount_col = _find_amount_column(row)
            continue

        joined = " ".join(row)
        match = REFERENCE_RE.search(joined)
        if not match:
            continue

        amount: Decimal | None = None
        if amount_col is not None and amount_col < len(row):
            amount = _parse_money(row[amount_col])
        if amount is None:
            for cell in row:
                if REFERENCE_RE.search(cell) or _DATE_RE.match(cell.strip()):
                    continue
                value = _parse_money(cell)
                if value is not None and value > 0:
                    amount = value
                    break

        lines.append(StatementLine(_normalise_reference(match), amount, joined.strip()))
    return lines


def preview_statement(db: Session, raw: bytes) -> dict:
    """Read-only: returns what would be confirmed. Never mutates anything."""
    from .credit_service import CREDIT_PACKAGES

    lines = parse_statement(raw)

    # Same reference twice on one statement (e.g. a customer paid in two
    # instalments) is summed into one row.
    grouped: dict[str, list[StatementLine]] = {}
    for line in lines:
        grouped.setdefault(line.reference, []).append(line)

    rows: list[ReconciliationRow] = []
    for reference, group in grouped.items():
        amounts = [l.amount_zar for l in group if l.amount_zar is not None]
        paid = sum(amounts, Decimal("0")) if amounts else None
        row = ReconciliationRow(
            reference=reference,
            status=UNKNOWN_REFERENCE,
            paid_zar=float(paid) if paid is not None else None,
            statement_lines=[l.raw for l in group],
        )

        attempt = (
            db.query(PaymentAttempt)
            .filter(PaymentAttempt.bank_reference == reference)
            .filter(PaymentAttempt.method == PaymentMethod.BANK_TRANSFER)
            .first()
        )
        if attempt is not None:
            user = db.get(User, attempt.user_id)
            package = CREDIT_PACKAGES.get(attempt.package_key)
            expected = Decimal(str(package["price_zar"])) if package else None
            row.attempt_id = attempt.id
            row.user_email = user.email if user else None
            row.package_key = attempt.package_key
            row.credits = attempt.credits
            row.expected_zar = float(expected) if expected is not None else None

            if attempt.status == PaymentStatus.SUCCEEDED:
                row.status = ALREADY_CONFIRMED
            elif attempt.status != PaymentStatus.PENDING:
                row.status = NOT_PENDING
            elif paid is None or expected is None or paid + _TOLERANCE < expected:
                row.status = UNDERPAID
            else:
                row.status = MATCH
        rows.append(row)

    order = {MATCH: 0, UNDERPAID: 1, UNKNOWN_REFERENCE: 2, NOT_PENDING: 3, ALREADY_CONFIRMED: 4}
    rows.sort(key=lambda r: (order[r.status], r.reference))
    return {
        "rows": [asdict(r) for r in rows],
        "summary": {
            "lines_with_reference": len(lines),
            "matches": sum(1 for r in rows if r.status == MATCH),
            "needs_review": sum(1 for r in rows if r.status in (UNDERPAID, UNKNOWN_REFERENCE, NOT_PENDING)),
            "already_confirmed": sum(1 for r in rows if r.status == ALREADY_CONFIRMED),
        },
    }
