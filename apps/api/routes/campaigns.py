"""
app/routes/campaigns.py

Admin-only bulk email campaigns, sent via services/campaign_worker.py
through the existing RQ job queue (services/job_queue.py) -- never sent
inline from a request handler, since a campaign's target list can have
thousands of recipients. No frontend screen yet; callable via
curl/Postman until an admin UI pass wires one up.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from deps import require_admin
from models import Campaign, CampaignRecipient, CampaignStatus, SubscriberList, User
from services import subscriber_service
from services.job_queue import get_queue
from services.rate_limiter import get_rate_limiter

router = APIRouter(prefix="/api/admin/campaigns", tags=["campaigns"])


class CreateCampaignRequest(BaseModel):
    name: str
    subject: str
    body_html: str
    subscriber_list_id: str


@router.post("", status_code=201)
def create_campaign(
    payload: CreateCampaignRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscriber_list = db.get(SubscriberList, payload.subscriber_list_id)
    if subscriber_list is None:
        raise HTTPException(status_code=404, detail="Unknown subscriber list")

    campaign = Campaign(
        name=payload.name,
        subject=payload.subject,
        body_html=payload.body_html,
        subscriber_list_id=payload.subscriber_list_id,
        created_by_user_id=admin.id,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return _campaign_summary(db, campaign)


@router.get("")
def list_campaigns(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    return {"campaigns": [_campaign_summary(db, c) for c in campaigns]}


@router.get("/{campaign_id}")
def get_campaign(campaign_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Unknown campaign")
    return _campaign_summary(db, campaign)


@router.get("/{campaign_id}/recipients")
def list_campaign_recipients(campaign_id: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Unknown campaign")
    recipients = db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign_id).all()
    return {
        "recipients": [
            {
                "id": r.id,
                "subscriber_id": r.subscriber_id,
                "status": r.status.value,
                "error": r.error,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            }
            for r in recipients
        ]
    }


@router.post("/{campaign_id}/send")
def send_campaign(
    campaign_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Idempotent against a repeated call: once a campaign has left DRAFT,
    a second send request is a no-op rather than re-queuing duplicate
    CampaignRecipient rows (which the unique(campaign, subscriber)
    constraint would reject anyway) or double-sending to anyone."""
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Unknown campaign")

    if campaign.status != CampaignStatus.DRAFT:
        return _campaign_summary(db, campaign)

    settings = get_settings()
    result = get_rate_limiter().hit(
        f"campaign_send:{admin.id}", settings.rate_limit_campaign_send_per_hour, window_seconds=3600
    )
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({settings.rate_limit_campaign_send_per_hour} sends/hour). Try again later.",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )

    recipients = subscriber_service.eligible_recipients_for_campaign(db, campaign)
    for subscriber in recipients:
        db.add(CampaignRecipient(campaign_id=campaign.id, subscriber_id=subscriber.id))

    campaign.status = CampaignStatus.QUEUED
    db.add(campaign)
    db.commit()

    get_queue().enqueue(
        "services.campaign_worker.send_campaign",
        campaign.id,
        job_timeout=settings.job_timeout_seconds,
        result_ttl=0,
        failure_ttl=3600,
    )

    db.refresh(campaign)
    return _campaign_summary(db, campaign)


def _campaign_summary(db: Session, campaign: Campaign) -> dict:
    recipient_count = db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign.id).count()
    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "subscriber_list_id": campaign.subscriber_list_id,
        "status": campaign.status.value,
        "recipient_count": recipient_count,
        "sent_at": campaign.sent_at.isoformat() if campaign.sent_at else None,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
    }
