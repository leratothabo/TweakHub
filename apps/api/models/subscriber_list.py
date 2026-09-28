"""
app/models/subscriber_list.py

SubscriberList is a named audience ("All Subscribers", "Newsletter",
a manually-curated segment); SubscriberListMembership is one row per
(list, subscriber) pairing, following the same "join-row per
relationship, with its own status/timestamps" pattern as
models/organization.py's OrganizationMember, rather than a bare bridge
table -- removing someone from a list should be an auditable event
(removed_at), not a silent row deletion.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class SubscriberList(Base):
    __tablename__ = "subscriber_lists"
    __table_args__ = (
        # At most one default list platform-wide -- see
        # services/subscriber_service.py's get_or_create_default_list().
        Index(
            "uq_subscriber_lists_one_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default = true"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<SubscriberList {self.name}>"


class MembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    REMOVED = "removed"


class SubscriberListMembership(Base):
    __tablename__ = "subscriber_list_memberships"
    __table_args__ = (
        UniqueConstraint("subscriber_list_id", "subscriber_id", name="uq_list_memberships_list_subscriber"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_list_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subscriber_lists.id"), index=True, nullable=False
    )
    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id"), index=True, nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(MembershipStatus), default=MembershipStatus.ACTIVE, nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<SubscriberListMembership list={self.subscriber_list_id} subscriber={self.subscriber_id} {self.status}>"
