"""SQLAlchemy models."""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

db = SQLAlchemy()


class Lead(db.Model):
    """A lead from the audit request or resource download form."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fname: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    submission_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'audit' | 'resource'
    resource_slug: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. 'cro-checklist'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Lead {self.email} ({self.submission_type})>"
