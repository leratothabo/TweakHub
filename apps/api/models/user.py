import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, String, Integer, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class PlanTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=True)  # ISO 3166-1 alpha-2
    plan_tier: Mapped[PlanTier] = mapped_column(Enum(PlanTier), default=PlanTier.FREE, nullable=False)
    credit_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Site-wide admin flag — currently only gates routes/admin.py's
    # bank-transfer confirmation endpoints (services/payment_service.py's
    # direct-EFT flow has no webhook, so a human has to confirm the
    # deposit landed). Deliberately no self-service way to grant this;
    # set it directly in the database for whoever should have access.
    # Unrelated to OrganizationMember.role (models/organization.py), which
    # is scoped to a single team, not the whole platform.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # -- Auth --
    # Nullable rather than required: leaves room for a future OAuth-only
    # signup path (social login) that never sets a local password. Every
    # signup through routes/auth.py today always sets this.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_token: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    email_verification_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    password_reset_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # -- Referrals (services/auth_service.py generates this at signup;
    # nullable only so a pre-existing row from before this column existed
    # doesn't break — every new signup always gets one) --
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=True)
    referred_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<User {self.email} plan={self.plan_tier} credits={self.credit_balance}>"
