"""
app/services/auth_service.py

Signup/login/verify-email/password-reset logic. Passwords are hashed with
bcrypt (never stored or logged in plaintext). Verification and reset
tokens are random URL-safe strings stored on the user row with an
expiry — simple and fine at this scale; move to a separate token table
with hashed tokens if abuse ever becomes a concern.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy.orm import Session

from config import get_settings
from models import User
from .credit_service import credit_service
from .email_service import email_service

EMAIL_VERIFICATION_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(hours=2)
SIGNUP_BONUS_CREDITS = 25

# A fixed bcrypt hash checked (and always loses) whenever login() has no
# real password_hash to compare against — see login()'s docstring for why.
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"tweakhub-timing-normalization", bcrypt.gensalt()).decode("utf-8")

# Uppercase letters + digits rather than secrets.token_urlsafe's base64
# alphabet — a referral code is meant to be read aloud, typed, or dropped
# into a chat message, so it skips '-'/'_' and stays case-insensitive-safe
# in practice (still generated/compared case-sensitively, but nothing in
# the alphabet collides visually the way 0/O or 1/l/I would).
REFERRAL_CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
REFERRAL_CODE_LENGTH = 8


class AuthError(Exception):
    """Raised for any user-facing auth failure — routes/auth.py turns these into 4xx responses."""


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    # SQLite (used in tests) doesn't preserve tzinfo on round-trip; treat a
    # naive timestamp as UTC rather than raising on the comparison.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now


def generate_referral_code(db: Session) -> str:
    """Module-level (not a method on AuthService — it doesn't need any
    instance state) so services/oauth_service.py can reuse it for
    Google-signup accounts without reaching into AuthService's
    internals."""
    for _ in range(10):
        code = "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH))
        if db.query(User).filter(User.referral_code == code).first() is None:
            return code
    # Astronomically unlikely at this alphabet size (32^8), but fail
    # loudly rather than silently signing someone up with no code if it
    # ever does happen.
    raise AuthError("Could not generate a unique referral code — please try again")


class AuthService:
    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False

    def signup(
        self, db: Session, email: str, password: str, full_name: str | None,
        referral_code: str | None = None,
    ) -> User:
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters")

        existing = db.query(User).filter(User.email == email).first()
        if existing is not None:
            raise AuthError("An account with this email already exists")

        referrer = None
        if referral_code:
            referrer = db.query(User).filter(User.referral_code == referral_code.upper()).first()
            # An unrecognized/stale/mistyped code is silently ignored
            # rather than rejecting the signup — nobody should be blocked
            # from creating an account by a bad ?ref= link.

        user = User(
            email=email,
            full_name=full_name,
            password_hash=self.hash_password(password),
            credit_balance=SIGNUP_BONUS_CREDITS,
            is_email_verified=False,
            email_verification_token=secrets.token_urlsafe(32),
            email_verification_expires_at=datetime.now(timezone.utc) + EMAIL_VERIFICATION_TTL,
            referral_code=generate_referral_code(db),
            referred_by_user_id=referrer.id if referrer else None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        email_service.send_verification_email(user.email, user.email_verification_token)
        return user

    def login(self, db: Session, email: str, password: str) -> User:
        # bcrypt's check is deliberately slow (~100ms+), and the original
        # `user is None or not user.password_hash or not
        # verify_password(...)` short-circuited straight past that check
        # for an unregistered email or a Google-OAuth-only account
        # (password_hash is None — set at oauth_service.py's signup
        # path), while a real local-password account always paid the
        # bcrypt cost. Same generic error message either way, but
        # different response latency — an attacker can time a guessed
        # email against a wrong password and tell "no local-password
        # account" (fast) apart from "account exists" (slow), enumerating
        # registered emails before a credential-stuffing pass. Always
        # running one bcrypt check — against a fixed dummy hash when
        # there's no real one — keeps the two paths' timing comparable.
        user = db.query(User).filter(User.email == email).first()
        password_hash = user.password_hash if user is not None else None
        password_ok = self.verify_password(password, password_hash or _DUMMY_PASSWORD_HASH)
        if user is None or not password_hash or not password_ok:
            raise AuthError("Invalid email or password")

        # Email verification is enforced everywhere except local dev, so
        # the signup -> login loop is testable without a real mail
        # provider configured (see services/email_service.py).
        if not user.is_email_verified and get_settings().node_env != "development":
            raise AuthError("Please verify your email before signing in")

        return user

    def verify_email(self, db: Session, token: str) -> User:
        user = db.query(User).filter(User.email_verification_token == token).first()
        if user is None:
            raise AuthError("Invalid or expired verification link")
        if _is_expired(user.email_verification_expires_at):
            raise AuthError("Verification link has expired — request a new one")

        # Atomic conditional UPDATE, not load-then-set-then-commit.
        # _grant_referral_bonus_if_applicable() has no separate "already
        # granted" flag — its whole safety against a double grant rests
        # on this token only ever being consumable once, on the
        # assumption that a plain SELECT-then-mutate-then-commit can't
        # race. It can: two concurrent POST /api/auth/verify-email calls
        # carrying the same still-valid token can both pass the SELECT
        # above before either commits (ordinary read-committed
        # semantics), and both would then call the grant. The UPDATE's
        # WHERE clause re-checks email_verification_token at write time
        # (which takes a row lock), so only one of two racing requests
        # gets rowcount == 1 and proceeds to grant the bonus; the other
        # gets 0 and is told the link was already used — the same
        # response a legitimate double-submit would get.
        updated = (
            db.query(User)
            .filter(User.id == user.id, User.email_verification_token == token)
            .update(
                {
                    "is_email_verified": True,
                    "email_verification_token": None,
                    "email_verification_expires_at": None,
                },
                synchronize_session=False,
            )
        )
        if updated == 0:
            db.rollback()
            raise AuthError("Invalid or expired verification link")
        db.commit()
        db.refresh(user)

        self._grant_referral_bonus_if_applicable(db, user)
        return user

    def _grant_referral_bonus_if_applicable(self, db: Session, user: User) -> None:
        """Bonus credits go to both sides of a referral, but only once —
        gated on the invitee's email verification (not signup itself) so a
        burst of throwaway unverified signups can't be used to farm free
        credits for either party. Safe against replay without any extra
        "already granted" flag: verify_email() can only ever succeed once
        per user (the token is cleared on first use, and every call after
        that hits the "Invalid or expired" branch above), so this method
        only ever runs once per referred_by_user_id."""
        if not user.referred_by_user_id:
            return
        referrer = db.get(User, user.referred_by_user_id)
        if referrer is None:
            return  # referrer's account was somehow deleted since signup — nothing to credit

        settings = get_settings()
        credit_service.grant_bonus_credits(
            db, user, settings.referral_bonus_credits_invitee,
            note=f"Referral bonus for signing up via {referrer.email}'s invite",
        )
        credit_service.grant_bonus_credits(
            db, referrer, settings.referral_bonus_credits_referrer,
            note=f"Referral bonus — {user.email} verified their account",
        )

    def request_password_reset(self, db: Session, email: str) -> None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            return  # don't reveal whether the email is registered

        user.password_reset_token = secrets.token_urlsafe(32)
        user.password_reset_expires_at = datetime.now(timezone.utc) + PASSWORD_RESET_TTL
        db.add(user)
        db.commit()

        email_service.send_password_reset_email(user.email, user.password_reset_token)

    def reset_password(self, db: Session, token: str, new_password: str) -> User:
        if len(new_password) < 8:
            raise AuthError("Password must be at least 8 characters")

        user = db.query(User).filter(User.password_reset_token == token).first()
        if user is None:
            raise AuthError("Invalid or expired reset link")
        if _is_expired(user.password_reset_expires_at):
            raise AuthError("Reset link has expired — request a new one")

        user.password_hash = self.hash_password(new_password)
        user.password_reset_token = None
        user.password_reset_expires_at = None
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


auth_service = AuthService()
