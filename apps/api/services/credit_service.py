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

from models import CreditTransaction, CreditTransactionType, Organization, PaymentMethod, User
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

    def refund_credits(self, db: Session, user: User, tool_name: str, amount: int, note: str) -> CreditTransaction:
        """Return credits for a failed job — to whichever pool
        spend_credits() originally charged (the user's org, if any)."""
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
        admin confirms the deposit (routes/admin.py). OZOW is its own
        instant-EFT gateway — a payment_url like DPO's, but credited off
        its own notify webhook (routes/payments.py's ozow_notify), not
        DPO's. Every other method goes through DPO — credits granted only
        after webhook/callback confirmation. The `payment_method` key is
        what the frontend branches on to tell these apart."""
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

        if method == PaymentMethod.OZOW:
            attempt, payment_url = payment_service.create_ozow_attempt(
                db=db,
                user=user,
                package_key=package_key,
                amount_usd=package["price_usd"],
                amount_zar=package["price_zar"],
                credits=package["credits"],
                bank_reference=f"TweakHub {package['credits']} credits",
            )
            return {
                "payment_attempt_id": attempt.id,
                "payment_method": "ozow",
                "payment_url": payment_url,
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
        """Called once a PaymentAttempt is confirmed SUCCEEDED by the DPO webhook — never speculatively."""
        if attempt.credits_granted:
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
