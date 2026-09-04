"""
HTTP-level tests for /api/organizations/* (routes/organizations.py).
services/organization_service.py's own tests cover the lifecycle logic in
depth — these confirm the route wiring: auth requirement, status codes,
response shape, and a full create -> invite -> accept round trip through
real HTTP requests.
"""


def _signup_and_login(client, email: str) -> str:
    client.post("/api/auth/signup", json={"email": email, "password": "correct horse battery"})
    resp = client.post("/api/auth/login", json={"email": email, "password": "correct horse battery"})
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_get_my_organization_404s_for_a_solo_user(client):
    token = _signup_and_login(client, "solo-route@example.com")
    resp = client.get("/api/organizations/me", headers=_auth(token))
    assert resp.status_code == 404


def test_create_organization_requires_auth(client):
    resp = client.post("/api/organizations", json={"name": "Acme Co"})
    assert resp.status_code == 401


def test_create_organization_then_get_me(client):
    token = _signup_and_login(client, "create-owner@example.com")
    resp = client.post("/api/organizations", json={"name": "Acme Co"}, headers=_auth(token))
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Acme Co"
    assert body["plan_tier"] == "business"
    assert body["credit_balance"] == 0

    me = client.get("/api/organizations/me", headers=_auth(token)).json()
    assert me["name"] == "Acme Co"
    assert me["my_role"] == "owner"
    assert len(me["members"]) == 1
    assert me["members"][0]["status"] == "joined"


def test_create_organization_rejects_free_tier(client):
    token = _signup_and_login(client, "free-tier-owner@example.com")
    resp = client.post(
        "/api/organizations", json={"name": "Acme Co", "plan_tier": "free"}, headers=_auth(token)
    )
    assert resp.status_code == 400


def test_create_organization_rejects_a_second_org_for_the_same_user(client):
    token = _signup_and_login(client, "double-owner@example.com")
    client.post("/api/organizations", json={"name": "First Org"}, headers=_auth(token))
    resp = client.post("/api/organizations", json={"name": "Second Org"}, headers=_auth(token))
    assert resp.status_code == 400


def test_invite_then_accept_round_trip(client, db_session):
    owner_token = _signup_and_login(client, "route-invite-owner@example.com")
    client.post("/api/organizations", json={"name": "Acme Co"}, headers=_auth(owner_token))

    invite_resp = client.post(
        "/api/organizations/invite",
        json={"email": "route-invitee@example.com"},
        headers=_auth(owner_token),
    )
    assert invite_resp.status_code == 201
    assert invite_resp.json()["status"] == "invited"

    # The invite token isn't in the HTTP response (it goes out over email
    # — see services/email_service.py's send_org_invite_email) so pull it
    # from the DB the way a test double for the email backend would.
    from models import OrganizationMember

    member_row = (
        db_session.query(OrganizationMember)
        .filter(OrganizationMember.email == "route-invitee@example.com")
        .first()
    )
    assert member_row is not None
    assert member_row.invite_token is not None

    invitee_token = _signup_and_login(client, "route-invitee@example.com")
    accept_resp = client.post(
        "/api/organizations/accept-invite",
        json={"token": member_row.invite_token},
        headers=_auth(invitee_token),
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "joined"

    me = client.get("/api/organizations/me", headers=_auth(invitee_token)).json()
    assert me["name"] == "Acme Co"
    assert me["my_role"] == "member"
    assert len(me["members"]) == 2


def test_invite_requires_admin_or_owner(client, db_session):
    owner_token = _signup_and_login(client, "route-invite-owner-2@example.com")
    client.post("/api/organizations", json={"name": "Acme Co"}, headers=_auth(owner_token))
    client.post(
        "/api/organizations/invite",
        json={"email": "plain-member-route@example.com"},
        headers=_auth(owner_token),
    )

    from models import OrganizationMember

    member_row = (
        db_session.query(OrganizationMember)
        .filter(OrganizationMember.email == "plain-member-route@example.com")
        .first()
    )
    invitee_token = _signup_and_login(client, "plain-member-route@example.com")
    client.post(
        "/api/organizations/accept-invite",
        json={"token": member_row.invite_token},
        headers=_auth(invitee_token),
    )

    resp = client.post(
        "/api/organizations/invite",
        json={"email": "blocked-route-invitee@example.com"},
        headers=_auth(invitee_token),
    )
    assert resp.status_code == 400


def test_remove_member(client, db_session):
    owner_token = _signup_and_login(client, "route-remove-owner@example.com")
    client.post("/api/organizations", json={"name": "Acme Co"}, headers=_auth(owner_token))
    client.post(
        "/api/organizations/invite",
        json={"email": "route-removable@example.com"},
        headers=_auth(owner_token),
    )

    from models import OrganizationMember

    member_row = (
        db_session.query(OrganizationMember)
        .filter(OrganizationMember.email == "route-removable@example.com")
        .first()
    )
    invitee_token = _signup_and_login(client, "route-removable@example.com")
    client.post(
        "/api/organizations/accept-invite",
        json={"token": member_row.invite_token},
        headers=_auth(invitee_token),
    )
    db_session.refresh(member_row)

    remove_resp = client.delete(
        f"/api/organizations/members/{member_row.id}", headers=_auth(owner_token)
    )
    assert remove_resp.status_code == 200

    me = client.get("/api/organizations/me", headers=_auth(owner_token)).json()
    assert len(me["members"]) == 1


def test_balance_endpoint_reports_org_pool_for_a_member(client, db_session):
    owner_token = _signup_and_login(client, "route-balance-owner@example.com")
    org_resp = client.post("/api/organizations", json={"name": "Acme Co"}, headers=_auth(owner_token))

    from models import Organization

    org = db_session.query(Organization).filter(Organization.id == org_resp.json()["id"]).first()
    org.credit_balance = 500
    db_session.add(org)
    db_session.commit()

    balance = client.get("/api/credits/balance", headers=_auth(owner_token)).json()
    assert balance["credit_balance"] == 500
