"""
Tests for services/subscriber_service.py and the public
routes/subscribers.py endpoints built on it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (  # noqa: E402
    MembershipStatus,
    Subscriber,
    SubscriberListMembership,
    SubscriberSource,
    SubscriberStatus,
)
from services import subscriber_service  # noqa: E402
from services.auth_service import auth_service  # noqa: E402


def test_create_or_update_subscriber_upserts_by_email(db_session):
    first = subscriber_service.create_or_update_subscriber(
        db_session, "alice@example.com", source=SubscriberSource.NEWSLETTER_FORM,
        marketing_consent=True, consent_source="newsletter_form",
    )
    second = subscriber_service.create_or_update_subscriber(
        db_session, "alice@example.com", source=SubscriberSource.NEWSLETTER_FORM,
        marketing_consent=True, consent_source="newsletter_form",
    )
    assert first.id == second.id
    assert db_session.query(Subscriber).filter(Subscriber.email == "alice@example.com").count() == 1


def test_create_or_update_subscriber_links_user_id_on_later_signup(db_session):
    subscriber_service.create_or_update_subscriber(
        db_session, "bob@example.com", source=SubscriberSource.NEWSLETTER_FORM,
        marketing_consent=True, consent_source="newsletter_form",
    )
    user = auth_service.signup(db_session, "bob@example.com", "correct horse battery", None)

    subscriber = db_session.query(Subscriber).filter(Subscriber.email == "bob@example.com").first()
    assert subscriber.user_id == user.id


def _list_membership(db_session, subscriber_list_id, subscriber_id):
    return (
        db_session.query(SubscriberListMembership)
        .filter_by(subscriber_list_id=subscriber_list_id, subscriber_id=subscriber_id)
        .first()
    )


def test_signup_with_consent_creates_default_list_membership(db_session):
    auth_service.signup(db_session, "consenting@example.com", "correct horse battery", None, marketing_consent=True)

    subscriber = db_session.query(Subscriber).filter(Subscriber.email == "consenting@example.com").first()
    assert subscriber.marketing_consent is True
    assert subscriber.consent_given_at is not None

    default_list = subscriber_service.get_or_create_default_list(db_session)
    membership = _list_membership(db_session, default_list.id, subscriber.id)
    assert membership is not None
    assert membership.status == MembershipStatus.ACTIVE


def test_signup_without_consent_creates_no_list_membership(db_session):
    auth_service.signup(db_session, "silent@example.com", "correct horse battery", None)

    subscriber = db_session.query(Subscriber).filter(Subscriber.email == "silent@example.com").first()
    assert subscriber.marketing_consent is False
    assert subscriber.consent_given_at is None

    default_list = subscriber_service.get_or_create_default_list(db_session)
    membership = _list_membership(db_session, default_list.id, subscriber.id)
    assert membership is None


def test_unsubscribe_globally_is_idempotent(db_session):
    subscriber = subscriber_service.create_or_update_subscriber(
        db_session, "leaving@example.com", source=SubscriberSource.NEWSLETTER_FORM,
        marketing_consent=True, consent_source="newsletter_form",
    )
    subscriber_service.unsubscribe_globally(db_session, subscriber)
    subscriber_service.unsubscribe_globally(db_session, subscriber)  # second call must not raise

    db_session.refresh(subscriber)
    assert subscriber.status == SubscriberStatus.UNSUBSCRIBED


def test_add_to_list_is_idempotent_and_reactivates_after_removal(db_session):
    subscriber = subscriber_service.create_or_update_subscriber(
        db_session, "member@example.com", source=SubscriberSource.MANUAL,
        marketing_consent=True, consent_source="admin_manual_add",
    )
    subscriber_list = subscriber_service.get_or_create_default_list(db_session)

    m1 = subscriber_service.add_to_list(db_session, subscriber_list, subscriber)
    m2 = subscriber_service.add_to_list(db_session, subscriber_list, subscriber)
    assert m1.id == m2.id

    subscriber_service.remove_from_list(db_session, subscriber_list, subscriber)
    m3 = subscriber_service.add_to_list(db_session, subscriber_list, subscriber)
    assert m3.id == m1.id
    assert m3.status == MembershipStatus.ACTIVE


def test_newsletter_signup_route_requires_consent(client):
    res = client.post("/api/subscribers/newsletter-signup", json={"email": "nope@example.com", "consent": False})
    assert res.status_code == 400


def test_newsletter_signup_route_creates_subscriber(client, db_session):
    res = client.post("/api/subscribers/newsletter-signup", json={"email": "yes@example.com", "consent": True})
    assert res.status_code == 201

    subscriber = db_session.query(Subscriber).filter(Subscriber.email == "yes@example.com").first()
    assert subscriber is not None
    assert subscriber.marketing_consent is True


def test_unsubscribe_route_is_idempotent_for_unknown_token(client):
    res = client.post("/api/subscribers/unsubscribe", json={"token": "not-a-real-token"})
    assert res.status_code == 200


def test_unsubscribe_route_unsubscribes_by_token(client, db_session):
    client.post("/api/subscribers/newsletter-signup", json={"email": "tokened@example.com", "consent": True})
    subscriber = db_session.query(Subscriber).filter(Subscriber.email == "tokened@example.com").first()

    res = client.post("/api/subscribers/unsubscribe", json={"token": subscriber.unsubscribe_token})
    assert res.status_code == 200

    db_session.refresh(subscriber)
    assert subscriber.status == SubscriberStatus.UNSUBSCRIBED
