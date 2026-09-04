"""
HTTP-level tests for the referral flow: signup's `ref` field and
GET /api/auth/referral. services/auth_service.py's unit tests cover the
bonus-crediting logic itself in more depth — these confirm the route
wiring (payload field name, response shape, auth requirement).
"""


def test_get_referral_requires_auth(client):
    resp = client.get("/api/auth/referral")
    assert resp.status_code == 401


def test_signup_then_get_referral_returns_code_and_link(client):
    resp = client.post(
        "/api/auth/signup",
        json={"email": "route-ref@example.com", "password": "correct horse battery"},
    )
    assert resp.status_code == 201

    login_resp = client.post(
        "/api/auth/login", json={"email": "route-ref@example.com", "password": "correct horse battery"}
    )
    token = login_resp.json()["access_token"]

    resp = client.get("/api/auth/referral", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["referral_code"]) == 8
    assert body["referral_code"] in body["referral_link"]
    assert body["bonus_credits_invitee"] == 25
    assert body["bonus_credits_referrer"] == 50


def test_signup_with_ref_query_field_links_referrer(client, db_session):
    from models import User

    referrer_resp = client.post(
        "/api/auth/signup",
        json={"email": "ref-referrer@example.com", "password": "correct horse battery"},
    )
    assert referrer_resp.status_code == 201
    referrer = db_session.query(User).filter(User.email == "ref-referrer@example.com").first()

    invitee_resp = client.post(
        "/api/auth/signup",
        json={
            "email": "ref-invitee@example.com",
            "password": "correct horse battery",
            "ref": referrer.referral_code,
        },
    )
    assert invitee_resp.status_code == 201

    invitee = db_session.query(User).filter(User.email == "ref-invitee@example.com").first()
    assert invitee.referred_by_user_id == referrer.id


def test_signup_with_bogus_ref_still_succeeds(client):
    resp = client.post(
        "/api/auth/signup",
        json={
            "email": "bogus-ref@example.com",
            "password": "correct horse battery",
            "ref": "TOTALLYFAKE",
        },
    )
    assert resp.status_code == 201
