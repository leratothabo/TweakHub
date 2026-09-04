"""
app/routes/organizations.py

Team/business multi-seat accounts — HTTP layer over
services/organization_service.py. See that module's docstring and
models/organization.py for the v1 simplification (a user belongs to at
most one organization) this whole feature is built around.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from db import get_db
from deps import get_current_user
from models import Organization, OrgRole, PlanTier, User
from services import organization_service
from services.organization_service import OrgError

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


def _member_out(member) -> dict:
    return {
        "id": member.id,
        "email": member.email,
        "role": member.role.value,
        "status": "joined" if member.joined_at else "invited",
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
    }


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # BUSINESS is the default and the common case; ENTERPRISE is accepted
    # too (both are shared-pool tiers — see
    # organization_service.ELIGIBLE_ORG_PLAN_TIERS).
    plan_tier: PlanTier = PlanTier.BUSINESS


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.MEMBER


class AcceptInviteRequest(BaseModel):
    token: str


def _require_membership(db: Session, user: User):
    membership = organization_service.get_membership(db, user)
    if membership is None:
        raise HTTPException(status_code=404, detail="You don't belong to an organization")
    return membership


@router.post("", status_code=201)
def create_organization(
    payload: CreateOrganizationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        org = organization_service.create_organization(db, user, payload.name, payload.plan_tier)
    except OrgError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"id": org.id, "name": org.name, "plan_tier": org.plan_tier.value, "credit_balance": org.credit_balance}


@router.get("/me")
def get_my_organization(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """404s (not a 200 with null fields) when the user doesn't belong to
    an org — lets the frontend treat "show the create-org form" as the
    plain not-found branch rather than parsing a nullable payload."""
    membership = _require_membership(db, user)
    org = db.get(Organization, membership.organization_id)
    return {
        "id": org.id,
        "name": org.name,
        "plan_tier": org.plan_tier.value,
        "credit_balance": org.credit_balance,
        "my_role": membership.role.value,
        "members": [_member_out(m) for m in organization_service.list_members(db, org)],
    }


@router.post("/invite", status_code=201)
def invite_member(
    payload: InviteMemberRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = _require_membership(db, user)
    org = db.get(Organization, membership.organization_id)
    try:
        member = organization_service.invite_member(db, org, membership, payload.email, payload.role)
    except OrgError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _member_out(member)


@router.post("/accept-invite")
def accept_invite(
    payload: AcceptInviteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        member = organization_service.accept_invite(db, payload.token, user)
    except OrgError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _member_out(member)


@router.delete("/members/{member_id}")
def remove_member(
    member_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = _require_membership(db, user)
    org = db.get(Organization, membership.organization_id)
    try:
        organization_service.remove_member(db, org, membership, member_id)
    except OrgError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"message": "Member removed"}
