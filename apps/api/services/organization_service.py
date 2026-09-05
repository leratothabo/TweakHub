"""
app/services/organization_service.py

Team/business multi-seat accounts — first cut. See models/organization.py
for the schema and its v1 simplification (a user belongs to at most one
organization). This module owns the lifecycle: create an org, invite a
member by email, accept an invite, list/remove members. The actual
shared-credit-pool billing lives in services/credit_service.py — this
module just answers "does this user belong to an org, and with what
role", which credit_service consults to pick a billing target.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Organization, OrganizationMember, OrgRole, PlanTier, User
from .email_service import email_service

INVITE_TTL = timedelta(days=7)
# Multi-seat billing is the whole point of an org — reject FREE/PRO here
# rather than silently accepting a tier where a shared pool doesn't apply.
ELIGIBLE_ORG_PLAN_TIERS = (PlanTier.BUSINESS, PlanTier.ENTERPRISE)


class OrgError(Exception):
    """Raised for any user-facing organization failure — routes/organizations.py turns these into 4xx responses."""


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < now


def get_membership(db: Session, user: User) -> OrganizationMember | None:
    """The user's own (joined, not just invited) membership row, if any —
    None for a user who has never joined an org, or whose only rows are
    still-pending invites."""
    return (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user.id, OrganizationMember.joined_at.isnot(None))
        .first()
    )


def get_organization_for_user(db: Session, user: User) -> Organization | None:
    membership = get_membership(db, user)
    if membership is None:
        return None
    return db.get(Organization, membership.organization_id)


def create_organization(db: Session, owner: User, name: str, plan_tier: PlanTier = PlanTier.BUSINESS) -> Organization:
    if get_membership(db, owner) is not None:
        raise OrgError("You already belong to an organization — see models/organization.py's v1 note")
    if plan_tier not in ELIGIBLE_ORG_PLAN_TIERS:
        raise OrgError(f"Organizations require the business or enterprise plan, not {plan_tier.value}")
    if not name or not name.strip():
        raise OrgError("Organization name is required")

    org = Organization(name=name.strip(), plan_tier=plan_tier, credit_balance=0)
    db.add(org)
    db.commit()
    db.refresh(org)

    owner_membership = OrganizationMember(
        organization_id=org.id,
        user_id=owner.id,
        email=owner.email,
        role=OrgRole.OWNER,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(owner_membership)
    db.commit()
    return org


def list_members(db: Session, org: Organization) -> list[OrganizationMember]:
    return (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == org.id)
        .order_by(OrganizationMember.created_at.asc())
        .all()
    )


def invite_member(
    db: Session, org: Organization, inviter_membership: OrganizationMember, email: str, role: OrgRole = OrgRole.MEMBER
) -> OrganizationMember:
    if inviter_membership.role not in (OrgRole.OWNER, OrgRole.ADMIN):
        raise OrgError("Only an owner or admin can invite members")
    if role == OrgRole.OWNER:
        raise OrgError("An organization can only have one owner")

    email = email.strip().lower()
    existing = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == org.id, OrganizationMember.email == email)
        .first()
    )
    if existing is not None:
        raise OrgError(
            "already a member" if existing.joined_at else "already invited and awaiting acceptance"
        )

    member = OrganizationMember(
        organization_id=org.id,
        email=email,
        role=role,
        invite_token=secrets.token_urlsafe(32),
        invite_expires_at=datetime.now(timezone.utc) + INVITE_TTL,
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    email_service.send_org_invite_email(email, org.name, member.invite_token)
    return member


def accept_invite(db: Session, token: str, accepting_user: User) -> OrganizationMember:
    member = db.query(OrganizationMember).filter(OrganizationMember.invite_token == token).first()
    if member is None:
        raise OrgError("Invalid or expired invite link")
    if _is_expired(member.invite_expires_at):
        raise OrgError("Invite link has expired — ask an admin to send a new one")
    if member.email.lower() != accepting_user.email.lower():
        raise OrgError("This invite was sent to a different email address")
    if get_membership(db, accepting_user) is not None:
        raise OrgError("You already belong to an organization — see models/organization.py's v1 note")

    member.user_id = accepting_user.id
    member.joined_at = datetime.now(timezone.utc)
    member.invite_token = None
    member.invite_expires_at = None
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        # The get_membership() check above is a plain SELECT with no
        # lock — two concurrent accept-invite calls for two different
        # pending invites to the same email (plausible: a shared work
        # email invited by two different orgs) can both pass it before
        # either commits. models/organization.py's
        # uq_org_members_one_org_per_user partial index is what actually
        # stops the second one from creating a second joined membership;
        # this is that constraint violation surfacing as a clean 4xx
        # instead of an unhandled 500.
        db.rollback()
        raise OrgError("You already belong to an organization — see models/organization.py's v1 note")
    db.refresh(member)
    return member


def remove_member(db: Session, org: Organization, actor_membership: OrganizationMember, target_member_id: str) -> None:
    if actor_membership.role not in (OrgRole.OWNER, OrgRole.ADMIN):
        raise OrgError("Only an owner or admin can remove members")

    target = db.get(OrganizationMember, target_member_id)
    if target is None or target.organization_id != org.id:
        raise OrgError("No such member")
    if target.role == OrgRole.OWNER:
        raise OrgError("The owner can't be removed")
    if target.id == actor_membership.id:
        raise OrgError("Use a different owner/admin account to remove your own membership")

    db.delete(target)
    db.commit()
