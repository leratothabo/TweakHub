"""
app/services/campaign_worker.py

send_campaign() is the actual work behind a campaign send -- what
services/job_queue.py's queue calls after routes/campaigns.py's
POST .../send enqueues it. Same shape as services/job_worker.py: opens
its own SessionLocal (there's no HTTP request to scope a session to
here), never called synchronously from a request handler since a
campaign can target thousands of recipients.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import get_settings
from db import SessionLocal
from models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
    Subscriber,
    SubscriberStatus,
)
from services.brevo_service import BrevoServiceError, send_transactional_email

logger = logging.getLogger("tweakhub.campaign_worker")


def _unsubscribe_footer(subscriber: Subscriber) -> str:
    settings = get_settings()
    link = f"{settings.base_url}/unsubscribe?token={subscriber.unsubscribe_token}"
    return (
        f'<hr/><p style="font-size:12px;color:#888">'
        f'You are receiving this email from TweakHub. '
        f'<a href="{link}">Unsubscribe</a></p>'
    )


def send_campaign(campaign_id: str) -> None:
    db = SessionLocal()
    try:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            logger.error("send_campaign: no Campaign with id=%s", campaign_id)
            return

        campaign.status = CampaignStatus.SENDING
        db.add(campaign)
        db.commit()

        recipients = (
            db.query(CampaignRecipient)
            .filter(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.status == CampaignRecipientStatus.PENDING,
            )
            .all()
        )

        for recipient in recipients:
            # Re-check per recipient, not just once up front -- a send can
            # run for minutes across many rows, and a subscriber could
            # unsubscribe (or a prior recipient's send could reveal a bad
            # BREVO_API_KEY) mid-batch. One recipient's outcome never
            # aborts the rest of the loop.
            try:
                subscriber = db.get(Subscriber, recipient.subscriber_id)
                if subscriber is None or subscriber.status != SubscriberStatus.ACTIVE:
                    recipient.status = CampaignRecipientStatus.UNSUBSCRIBED
                    db.add(recipient)
                    db.commit()
                    continue

                html_content = campaign.body_html + _unsubscribe_footer(subscriber)
                message_id = send_transactional_email(
                    to_email=subscriber.email,
                    to_name=subscriber.full_name,
                    subject=campaign.subject,
                    html_content=html_content,
                )
                recipient.status = CampaignRecipientStatus.SENT
                recipient.brevo_message_id = message_id
                recipient.sent_at = datetime.now(timezone.utc)
                db.add(recipient)
                db.commit()
            except BrevoServiceError as exc:
                logger.warning("Campaign %s: recipient %s failed: %s", campaign.id, recipient.id, exc)
                recipient.status = CampaignRecipientStatus.FAILED
                recipient.error = str(exc)
                db.add(recipient)
                db.commit()
            except Exception:
                # Anything else unexpected for this one recipient --
                # logged, marked failed, loop continues. Never let one bad
                # row wedge the whole campaign in SENDING forever.
                logger.exception("Campaign %s: unexpected error for recipient %s", campaign.id, recipient.id)
                recipient.status = CampaignRecipientStatus.FAILED
                recipient.error = "Unexpected error"
                db.add(recipient)
                db.commit()

        # SENT means "the send process ran to completion" -- individual
        # recipient failures are visible per-row (CampaignRecipient.status),
        # not rolled up into the campaign's own status. Only a crash that
        # escapes this whole try block (caught below) marks the campaign
        # itself FAILED.
        campaign.status = CampaignStatus.SENT
        campaign.sent_at = datetime.now(timezone.utc)
        db.add(campaign)
        db.commit()
    except Exception:
        logger.exception("send_campaign: unhandled error for campaign %s", campaign_id)
        campaign = db.get(Campaign, campaign_id)
        if campaign is not None:
            campaign.status = CampaignStatus.FAILED
            db.add(campaign)
            db.commit()
        raise
    finally:
        db.close()
