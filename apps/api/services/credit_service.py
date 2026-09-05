"""
app/services/credit_service.py

Credit balance + pricing logic. Pulls per-tool base cost from
tools_catalog (the single source of truth also used by ToolRouter) rather
than duplicating a second pricing dict, and does every balance mutation
inside one DB transaction with a CreditTransaction audit row so a user's
`credit_balance` is always reconstructable from its transaction history.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import CreditTransaction, CreditTransactionType, Organization, PaymentAttempt, PaymentMethod, User
from . import organization_service
from .payment_service import BANK_TRANSFER_DETAILS, payment_service
from .tools_catalog import get_tool

CREDIT_PACKAGES = {
    "starter": {"credits": 100, "price_usd": 2.99, "price_zar": 55},
    "popular": {"credits": 500, "price_usd": 9.99, "price_zar": 185},
    "pro": {"credits": 2000, "price_usd": 29.99, "price_zar": 555},
    "business": {"credits": 10000, "price_usd": 99.99, "price_zar": 1850},
}


class InsufficientCreditsError(Exception):
    pass


class CreditService:
    def _billing_target(self, db: Session, user: User) -> User | Organization:
        """A member of an organization (services/organization_service.py)
        bills every tool run against that org's shared credit_balance
        instead of their own — this is the one place that decision gets
        made, so spend/refund/bonus and the balance shown in API
        responses can never disagree about which pool is authoritative."""
        org = organization_service.get_organization_for_user(db, user)
        return org if org is not None else user

    def get_effective_balance(self, db: Session, user: User) -> int:
        """What routes/tools.py and routes/credits.py should show as
        "your" balance — the org's shared pool for an org member, the
        user's own credit_balance otherwise."""
        return self._billing_target(db, user).credit_balance

    def get_credit_cost(self, tool_name: str, file_size_mb: float) -> int:
        """Calculate credit cost based on tool complexity and file size (MB)."""
        spec = get_tool(tool_name)
        cost = float(spec.base_credits) if spec else 10.0

        if file_size_mb > 100:
            cost *= 2
        elif file_size_mb > 50:
            cost *= 1.5

        return max(1, round(cost))

    def spend_credits(self, db: Session, user: User, tool_name: str, file_size_mb: float) -> CreditTransaction:
        """Deduct credits for running a tool — from the user's own
        balance, or from their organization's shared pool if they belong
        to one (see _billing_target()). Raises InsufficientCreditsError
        if that balance is too low."""
        cost = self.get_credit_cost(tool_name, file_size_mb)
        target = self._billing_target(db, user)
        if target.credit_balance < cost:
            who = "Organization" if isinstance(target, Organization) else "User"
            raise InsufficientCreditsError(
                f"Need {cost} credits, {who} {target.id} has {target.credit_balance}"
            )

        target.credit_balance -= cost
        tx = CreditTransaction(
            user_id=user.id,
            organization_id=target.id if isinstance(target, Organization) else None,
            type=CreditTransactionType.SPEND,
            amount=-cost,
            balance_after=target.credit_balance,
            tool_name=tool_name,
        )
        db.add(tx)
        db.add(target)
        db.commit()
        db.refresh(tx)
        return tx

    def refund_credits(
        self,
        db: Session,
        user: User,
        tool_name: str,
        amount: int,
        note: str,
        original_transaction: CreditTransaction | None = None,
    ) -> CreditTransaction:
        """Return credits for a failed job — to whichever pool
        spend_credits() *actually* charged, not whatever _billing_target()
        resolves to *right now*.

        Those can disagree: an async job can sit in the queue for minutes
        (see tool_timeouts.py), and org membership can change in that
        window — a member can be removed, or a user can join/leave an org
        — between when spend_credits() debited a pool and when the job
        later fails and gets refunded. Re-deriving the target at refund
        time silently moved credits from the org that was actually
        charged into whatever pool the user happens to belong to *now*
        (or vice versa), permanently draining the real payer and handing
        a free refund to an unrelated pool. Pass the original spend
        CreditTransaction (both call sites — routes/tools.py's sync path
        and job_worker.py's _fail_job — have it via
        ProcessingJob.credit_transaction_id) so the refund follows the
        transaction's own recorded organization_id instead.
        """
        if original_transaction is not None:
            if original_transaction.organization_id:
                target: User | Organization = (
                    db.get(Organization, original_transaction.organization_id)
                    # The org could have been deleted since the original
                    # spend (no cascade/delete path exists today, but
                    # don't assume that forever) — fall back to the
                    # best-effort current resolution rather than crash.
                    or self._billing_target(db, user)
                )
            else:
                # Originally billed to the user personally — refund that
                # same user directly, not whatever org they might have
                # joined since.
                target = db.get(User, original_transaction.user_id) or user
        else:
            # No original transaction available (a caller that predates
            # this parameter, or a manual/administrative refund with no
            # specific job behind it) — best-effort, same as before.
            target = self._billing_target(db, user)

        target.credit_balance += amount
        tx = CreditTransaction(
            user_id=user.id,
            organization_id=target.id if isinstance(target, Organization) else None,
            type=CreditTransactionType.REFUND,
            amount=amount,
            balance_after=target.credit_balance,
            tool_name=tool_name,
            note=note,
        )
        db.add(tx)
        db.add(target)
        db.commit()
        db.refresh(tx)
        return tx

    def grant_bonus_credits(self, db: Session, user: User, amount: int, note: str) -> CreditTransaction:
        """Referral bonuses (or any other promo credit) — same shape as
        refund_credits() but tagged BONUS so credit_transactions stays an
        honest audit trail of *why* a balance changed, not just that it
        did. Always lands on the named user's own credit_balance, even if
        they belong to an org — a referral bonus is earned by the person,
        not the team (unlike spend/refund, which follow whichever pool
        actually paid for the tool run)."""
        user.credit_balance += amount
        tx = CreditTransaction(
            user_id=user.id,
            type=CreditTransactionType.BONUS,
            amount=amount,
            balance_after=user.credit_balance,
            note=note,
        )
        db.add(tx)
        db.add(user)
        db.commit()
        db.refresh(tx)
        return tx

    def initiate_purchase(self, db: Session, user: User, package_key: str, method: PaymentMethod) -> dict:
        """Kick off a credit-package purchase. BANK_TRANSFER is a direct
        EFT — no gateway, no payment_url, credits granted only once an
        admin confirms the deposit (routes/admin.py). Every other method
        goes through DPO — credits granted only after webhook/callback
        confirmation (routes/payments.py). The `payment_method` key is
        what the frontend branches on to decide which of those two
        responses it got."""
        package = CREDIT_PACKAGES.get(package_key)
        if package is None:
            raise ValueError(f"Unknown credit package: {package_key}")

        if method == PaymentMethod.BANK_TRANSFER:
            attempt = payment_service.create_bank_transfer_attempt(
                db=db,
                user=user,
                package_key=package_key,
                amount_usd=package["price_usd"],
                credits=package["credits"],
            )
            return {
                "payment_attempt_id": attempt.id,
                "payment_method": "bank_transfer",
                "bank_reference": attempt.bank_reference,
                "bank_details": BANK_TRANSFER_DETAILS,
                "credits": package["credits"],
                "amount_usd": package["price_usd"],
            }

        attempt, payment_url = payment_service.create_payment_attempt(
            db=db,
            user=user,
            package_key=package_key,
            amount_usd=package["price_usd"],
            credits=package["credits"],
            method=method,
        )

        return {
            "payment_attempt_id": attempt.id,
            "payment_method": "dpo",
            "payment_url": payment_url,
            "credits": package["credits"],
            "amount_usd": package["price_usd"],
        }

    def grant_purchased_credits(self, db: Session, user: User, attempt) -> CreditTransaction:
        """Called once a PaymentAttempt is confirmed SUCCEEDED by the DPO
        webhook or an admin bank-transfer confirmation — never
        speculatively.

        Guards with an atomic conditional UPDATE, not a Python
        check-then-act on `attempt.credits_granted`. routes/payments.py's
        own docstring documents that DPO's browser redirect and its
        server-to-server webhook both land on the same endpoint for the
        same payment — i.e. two concurrent callers loading the same
        PENDING/just-SUCCEEDED attempt row is the normal case here, not a
        rare edge case, and the same double-click risk exists for
        routes/admin.py's manual confirm. Under a plain `if
        attempt.credits_granted: raise`, two requests that both load the
        row before either commits would both see `credits_granted=False`
        and both grant credits. The UPDATE's WHERE clause re-checks
        credits_granted at write time (which takes a row lock), so only
        one of two racing callers gets `rowcount == 1`; the other gets 0
        and raises the same ValueError it always did — the caller just
        needs to treat that as "someone else already granted it," not a
        real error (see routes/payments.py and routes/admin.py)."""
        updated = (
            db.query(PaymentAttempt)
            .filter(PaymentAttempt.id == attempt.id, PaymentAttempt.credits_granted.is_(False))
            .update({"credits_granted": True}, synchronize_session=False)
        )
        if updated == 0:
            db.rollback()
            raise ValueError(f"Credits already granted for payment_attempt {attempt.id}")

        user.credit_balance += attempt.credits
        tx = CreditTransaction(
            user_id=user.id,
            type=CreditTransactionType.PURCHASE,
            amount=attempt.credits,
            balance_after=user.credit_balance,
            payment_attempt_id=attempt.id,
            note=f"Purchased package {attempt.package_key}",
        )
        attempt.credits_granted = True
        db.add(tx)
        db.add(user)
        db.add(attempt)
        db.commit()
        db.refresh(tx)
        return tx


credit_service = CreditService()
