"""
Tests for routes/campaigns.py and the subscriber-list admin endpoints
added to routes/admin.py -- non-admin 403s on every route (same shape
as test_bank_transfer.py's admin assertions), and the send endpoint is
idempotent against a repeated call.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import User  # noqa: E402
from services import subscriber_service  # noqa: E402


def _signup_and_login(client, email: str) -> str:
    client.post("/api/auth/signup", json={"email": email, "password": "correct horse battery"})
    res = client.post("/api/auth/login", json={"email": email, "password": "correct horse battery"})
    return res.json()["access_token"]


def _make_admin_token(client, db_session, email: str) -> str:
    token = _signup_and_login(client, email)
    user = db_session.query(User).filter(User.email == email).first()
    user.is_admin = True
    db_session.add(user)
    db_session.commit()
    return token


def _default_list_id(db_session) -> str:
    return subscriber_service.get_or_create_default_list(db_session).id


def test_non_admin_gets_403_on_subscriber_list_routes(client, db_session):
    token = _signup_and_login(client, "regular@example.com")
    list_id = _default_list_id(db_session)

    assert client.get("/api/admin/subscriber-lists", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.post(
        "/api/admin/subscriber-lists", json={"name": "VIPs"}, headers={"Authorization": f"Bearer {token}"}
    ).status_code == 403
    assert client.get(
        f"/api/admin/subscriber-lists/{list_id}/subscribers", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 403


def test_non_admin_gets_403_on_campaign_routes(client, db_session):
    token = _signup_and_login(client, "regular2@example.com")
    list_id = _default_list_id(db_session)

    assert client.get("/api/admin/campaigns", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.post(
        "/api/admin/campaigns",
        json={"name": "X", "subject": "Y", "body_html": "<p>Z</p>", "subscriber_list_id": list_id},
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 403


def test_admin_can_create_and_list_subscriber_lists(client, db_session):
    token = _make_admin_token(client, db_session, "admin1@example.com")

    res = client.post(
        "/api/admin/subscriber-lists",
        json={"name": "VIPs", "description": "Big spenders"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    list_id = res.json()["id"]

    res = client.get("/api/admin/subscriber-lists", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    names = [lst["name"] for lst in res.json()["lists"]]
    assert "VIPs" in names

    res = client.post(
        f"/api/admin/subscriber-lists/{list_id}/subscribers",
        json={"emails": ["vip1@example.com", "vip2@example.com"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    assert res.json()["added"] == 2

    res = client.get(
        f"/api/admin/subscriber-lists/{list_id}/subscribers", headers={"Authorization": f"Bearer {token}"}
    )
    emails = [s["email"] for s in res.json()["subscribers"]]
    assert "vip1@example.com" in emails


def test_create_and_send_campaign_is_idempotent(client, db_session, monkeypatch):
    token = _make_admin_token(client, db_session, "admin2@example.com")
    list_id = _default_list_id(db_session)

    # Add one consenting subscriber to the default list so there's
    # something to send to.
    client.post(
        f"/api/admin/subscriber-lists/{list_id}/subscribers",
        json={"emails": ["target@example.com"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    res = client.post(
        "/api/admin/campaigns",
        json={"name": "Launch", "subject": "Hi", "body_html": "<p>Hi</p>", "subscriber_list_id": list_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    campaign_id = res.json()["id"]
    assert res.json()["status"] == "draft"

    monkeypatch.setattr(
        "routes.campaigns.get_queue",
        lambda: type("_Q", (), {"enqueue": staticmethod(lambda *a, **k: None)})(),
    )

    res = client.post(f"/api/admin/campaigns/{campaign_id}/send", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    assert res.json()["recipient_count"] == 1

    # Second send call against a non-draft campaign is a no-op, not a
    # duplicate enqueue or an error.
    res = client.post(f"/api/admin/campaigns/{campaign_id}/send", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    assert res.json()["recipient_count"] == 1
