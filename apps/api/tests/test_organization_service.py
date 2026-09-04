"""
Tests for services/organization_service.py — the team/business multi-seat
account lifecycle (create -> invite -> accept -> remove). Uses
auth_service.signup() to create real User rows rather than constructing
them by hand, same convention as test_auth_service.py.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import OrgRole, PlanTier  # noqa: E402
from services.auth_service import auth_service  # noqa: E402
from services.organization_service import (  # noqa: E402
    OrgError,
    accept_invite,
    create_organization,
    get_membership,
    get_organization_for_user,
    invite_member,
    list_members,
    remove_member,
)


def _signup(db_session, email: str):
    return auth_service.signup(db_session, email, "correct horse battery", None)


def test_create_organization_makes_owner_a_joined_member(db_session):
    owner = _signup(db_session, "org-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")

    assert org.plan_tier == PlanTier.BUSINESS
    assert org.credit_balance == 0

    membership = get_membership(db_session, owner)
    assert membership is not None
    assert membership.role == OrgRole.OWNER
    assert membership.joined_at is not None
    assert membership.email == owner.email


def test_create_organization_rejects_free_and_pro_tiers(db_session):
    owner = _signup(db_session, "org-owner-tier@example.com")
    with pytest.raises(OrgError, match="business or enterprise"):
        create_organization(db_session, owner, "Acme Co", plan_tier=PlanTier.FREE)


def test_create_organization_rejects_blank_name(db_session):
    owner = _signup(db_session, "org-owner-blank@example.com")
    with pytest.raises(OrgError, match="name is required"):
        create_organization(db_session, owner, "   ")


def test_user_cannot_belong_to_two_organizations(db_session):
    owner = _signup(db_session, "org-owner-two@example.com")
    create_organization(db_session, owner, "First Org")
    with pytest.raises(OrgError, match="already belong"):
        create_organization(db_session, owner, "Second Org")


def test_invite_then_accept_joins_the_org(db_session):
    owner = _signup(db_session, "invite-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    owner_membership = get_membership(db_session, owner)

    invitee = _signup(db_session, "invitee@example.com")
    invited = invite_member(db_session, org, owner_membership, invitee.email, OrgRole.MEMBER)
    assert invited.joined_at is None
    assert invited.invite_token is not None

    accepted = accept_invite(db_session, invited.invite_token, invitee)
    assert accepted.joined_at is not None
    assert accepted.user_id == invitee.id
    assert accepted.invite_token is None

    assert get_organization_for_user(db_session, invitee).id == org.id
    members = list_members(db_session, org)
    assert {m.email for m in members} == {owner.email, invitee.email}


def test_invite_rejects_non_admin_inviter(db_session):
    owner = _signup(db_session, "invite-owner-2@example.com")
    org = create_organization(db_session, owner, "Acme Co")

    member_user = _signup(db_session, "plain-member@example.com")
    member_membership = invite_member(db_session, org, get_membership(db_session, owner), member_user.email)
    accept_invite(db_session, member_membership.invite_token, member_user)
    plain_membership = get_membership(db_session, member_user)

    other_invitee = _signup(db_session, "blocked-invitee@example.com")
    with pytest.raises(OrgError, match="owner or admin"):
        invite_member(db_session, org, plain_membership, other_invitee.email)


def test_invite_rejects_duplicate_email(db_session):
    owner = _signup(db_session, "invite-owner-3@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    owner_membership = get_membership(db_session, owner)

    invite_member(db_session, org, owner_membership, "dup-invitee@example.com")
    with pytest.raises(OrgError, match="already invited"):
        invite_member(db_session, org, owner_membership, "dup-invitee@example.com")


def test_accept_invite_rejects_wrong_email(db_session):
    owner = _signup(db_session, "invite-owner-4@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    invited = invite_member(db_session, org, get_membership(db_session, owner), "meant-for-someone@example.com")

    wrong_user = _signup(db_session, "not-the-invitee@example.com")
    with pytest.raises(OrgError, match="different email"):
        accept_invite(db_session, invited.invite_token, wrong_user)


def test_accept_invite_rejects_expired_token(db_session):
    from datetime import datetime, timedelta, timezone

    owner = _signup(db_session, "invite-owner-5@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    invited = invite_member(db_session, org, get_membership(db_session, owner), "slow-invitee@example.com")
    invited.invite_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add(invited)
    db_session.commit()

    invitee = _signup(db_session, "slow-invitee@example.com")
    with pytest.raises(OrgError, match="expired"):
        accept_invite(db_session, invited.invite_token, invitee)


def test_accept_invite_rejects_bogus_token(db_session):
    someone = _signup(db_session, "bogus-token-user@example.com")
    with pytest.raises(OrgError, match="Invalid or expired"):
        accept_invite(db_session, "not-a-real-token", someone)


def test_remove_member_by_admin(db_session):
    owner = _signup(db_session, "remove-owner@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    owner_membership = get_membership(db_session, owner)

    member_user = _signup(db_session, "removable-member@example.com")
    invited = invite_member(db_session, org, owner_membership, member_user.email)
    accept_invite(db_session, invited.invite_token, member_user)
    assert len(list_members(db_session, org)) == 2

    remove_member(db_session, org, owner_membership, invited.id)
    assert len(list_members(db_session, org)) == 1
    assert get_membership(db_session, member_user) is None


def test_remove_member_cannot_remove_owner(db_session):
    owner = _signup(db_session, "remove-owner-2@example.com")
    org = create_organization(db_session, owner, "Acme Co")
    owner_membership = get_membership(db_session, owner)

    with pytest.raises(OrgError, match="owner can't be removed"):
        remove_member(db_session, org, owner_membership, owner_membership.id)


def test_get_organization_for_user_returns_none_for_solo_user(db_session):
    solo = _signup(db_session, "solo-user@example.com")
    assert get_organization_for_user(db_session, solo) is None
