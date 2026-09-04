"""
app/models/organization.py

Team/business multi-seat accounts — first cut (see
services/organization_service.py and docs/TODO.md for what's
deliberately simplified here vs. a fuller v2).

v1 simplification: a user belongs to at most one organization. There's no
separate "personal account vs. org context" switcher — once a user's
OrganizationMember row has joined_at set, services/credit_service.py bills
every tool run against the org's shared credit_balance instead of the
user's own. This keeps the data model and the billing-target resolution
in credit_service.py's _billing_target() simple (one lookup, not a
"current active org" selector) at the cost of not supporting someone who
belongs to two teams — a real limitation, called out here rather than
glossed over, and the natural place a v2 would extend this model.
"""
import enum
import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from .user import PlanTier


class OrgRole(str, enum.Enum):
    OWNER = "owner"    # created the org; only role that can't be removed
    ADMIN = "admin"    # can invite/remove members
    MEMBER = "member"  # can run tools against the shared pool, nothing else


def _new_invite_token() -> str:
    return secrets.token_urlsafe(32)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Multi-seat billing only makes sense above the individual plans —
    # organization_service.create_organization() rejects FREE/PRO here.
    plan_tier: Mapped[PlanTier] = mapped_column(Enum(PlanTier), default=PlanTier.BUSINESS, nullable=False)
    # The shared pool every member's tool runs draw from — see
    # credit_service.py's _billing_target(). Purchases
    # (POST /api/credits/purchase) still only ever target a User today;
    # topping up an org's pool directly is a v2 gap, noted in
    # docs/TODO.md rather than silently unsupported.
    credit_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Organization {self.name} plan={self.plan_tier} credits={self.credit_balance}>"


class OrganizationMember(Base):
    """One row per (organization, invited email) — created at invite time
    with user_id=None, filled in when services.organization_service.
    accept_invite() is called by a signed-in user whose own email matches.
    The OWNER's row is created directly (already joined) by
    create_organization(), skipping the invite step for the founder."""

    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_org_members_org_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), index=True, nullable=False
    )
    # Set once the invite is accepted; null while it's still pending.
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    # The invited address — always set (even after acceptance, so a
    # member list can be rendered without a join for the still-pending
    # rows). accept_invite() requires the accepting user's own email to
    # match this, case-insensitively.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[OrgRole] = mapped_column(Enum(OrgRole), default=OrgRole.MEMBER, nullable=False)

    invite_token: Mapped[str] = mapped_column(String(64), nullable=True, unique=True, index=True)
    invite_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        status = "joined" if self.joined_at else "invited"
        return f"<OrganizationMember {self.email} org={self.organization_id} role={self.role} {status}>"
