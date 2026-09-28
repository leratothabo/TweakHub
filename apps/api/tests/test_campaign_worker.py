"""
Tests for services/campaign_worker.py's send_campaign() — exercised
directly (no Redis/RQ in the loop), the same idiom test_job_worker.py
uses for run_processing_job(). services/brevo_service.send_transactional_email
is monkeypatched directly, matching this repo's "patch the one external
call" convention (e.g. conftest.py's fake_rate_limiter).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (  # noqa: E402
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    PlanTier,
    SubscriberSource,
    User,
)
from services import subscriber_service  # noqa: E402
from services.campaign_worker import send_campaign  # noqa: E402


def _make_admin(db_session) -> User:
    user = User(email="admin@example.com", credit_balance=0, plan_tier=PlanTier.FREE, is_admin=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_campaign(db_session, admin, *, emails: list[str]) -> Campaign:
    subscriber_list = subscriber_service.get_or_create_default_list(db_session)
    subscribers = []
    for email in emails:
        subscriber = subscriber_service.create_or_update_subscriber(
            db_session, email, source=SubscriberSource.MANUAL,
            marketing_consent=True, consent_source="admin_manual_add",
        )
        subscriber_service.add_to_list(db_session, subscriber_list, subscriber)
        subscribers.append(subscriber)

    campaign = Campaign(
        name="Test campaign", subject="Hello", body_html="<p>Hi there</p>",
        subscriber_list_id=subscriber_list.id, created_by_user_id=admin.id,
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    for subscriber in subscribers:
        db_session.add(CampaignRecipient(campaign_id=campaign.id, subscriber_id=subscriber.id))
    db_session.commit()
    return campaign


def test_send_campaign_succeeds_for_active_subscribers(db_session, monkeypatch):
    admin = _make_admin(db_session)
    campaign = _make_campaign(db_session, admin, emails=["a@example.com", "b@example.com"])

    monkeypatch.setattr(
        "services.campaign_worker.send_transactional_email",
        lambda **kwargs: "fake-message-id",
    )

    send_campaign(campaign.id)

    db_session.refresh(campaign)
    assert campaign.status == CampaignStatus.SENT
    assert campaign.sent_at is not None

    recipients = db_session.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign.id).all()
    assert len(recipients) == 2
    for r in recipients:
        assert r.status == CampaignRecipientStatus.SENT
        assert r.brevo_message_id == "fake-message-id"


def test_send_campaign_skips_unsubscribed_recipient_without_calling_brevo(db_session, monkeypatch):
    admin = _make_admin(db_session)
    campaign = _make_campaign(db_session, admin, emails=["staying@example.com", "leaving@example.com"])

    from models import Subscriber

    leaving_subscriber = db_session.query(Subscriber).filter(Subscriber.email == "leaving@example.com").first()
    subscriber_service.unsubscribe_globally(db_session, leaving_subscriber)

    calls = []

    def _fake_send(**kwargs):
        calls.append(kwargs["to_email"])
        return "fake-message-id"

    monkeypatch.setattr("services.campaign_worker.send_transactional_email", _fake_send)

    send_campaign(campaign.id)

    assert calls == ["staying@example.com"]

    recipients = {
        r.subscriber_id: r.status
        for r in db_session.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign.id).all()
    }
    assert recipients[leaving_subscriber.id] == CampaignRecipientStatus.UNSUBSCRIBED


def test_send_campaign_continues_after_one_recipient_fails(db_session, monkeypatch):
    from services.brevo_service import BrevoServiceError

    admin = _make_admin(db_session)
    campaign = _make_campaign(db_session, admin, emails=["fails@example.com", "succeeds@example.com"])

    def _fake_send(**kwargs):
        if kwargs["to_email"] == "fails@example.com":
            raise BrevoServiceError("simulated failure")
        return "fake-message-id"

    monkeypatch.setattr("services.campaign_worker.send_transactional_email", _fake_send)

    send_campaign(campaign.id)

    db_session.refresh(campaign)
    # The batch still completes -- one recipient's failure doesn't wedge
    # the campaign or abort the rest of the loop.
    assert campaign.status == CampaignStatus.SENT

    recipients = db_session.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign.id).all()
    succeeded = [r for r in recipients if r.status == CampaignRecipientStatus.SENT]
    failed = [r for r in recipients if r.status == CampaignRecipientStatus.FAILED]
    assert len(succeeded) == 1
    assert len(failed) == 1
    assert failed[0].error == "simulated failure"
