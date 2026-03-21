"""SQLAlchemy models — table names prefixed with cro_nurture_."""

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import relationship

from app.models import db


class CroNurtureSequence(db.Model):
    __tablename__ = "cro_nurture_sequence"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    steps = relationship(
        "CroNurtureSequenceStep",
        back_populates="sequence",
        order_by="CroNurtureSequenceStep.step_order",
        cascade="all, delete-orphan",
    )
    leads = relationship("CroNurtureLead", back_populates="sequence")


class CroNurtureSequenceStep(db.Model):
    __tablename__ = "cro_nurture_sequence_step"
    __table_args__ = (UniqueConstraint("sequence_id", "step_order", name="uq_cro_nurture_seq_step"),)

    id = db.Column(db.Integer, primary_key=True)
    sequence_id = db.Column(db.Integer, db.ForeignKey("cro_nurture_sequence.id"), nullable=False, index=True)
    step_order = db.Column(db.Integer, nullable=False)
    delay_after_previous_seconds = db.Column(db.Integer, nullable=False, default=0)
    instruction_prompt = db.Column(db.Text, nullable=False)
    allowed_facts = db.Column(db.JSON, nullable=True)
    model_name = db.Column(db.String(80), nullable=True)

    sequence = relationship("CroNurtureSequence", back_populates="steps")
    sends = relationship("CroNurtureEmailSend", back_populates="sequence_step")


class CroNurtureLead(db.Model):
    __tablename__ = "cro_nurture_lead"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    email = db.Column(db.String(255), nullable=False, index=True)
    first_name = db.Column(db.String(150), nullable=True)
    last_name = db.Column(db.String(150), nullable=True)
    site_url = db.Column(db.String(2000), nullable=False)

    cro_scan_payload = db.Column(db.JSON, nullable=True)
    enrichment_status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    enrichment_error = db.Column(db.Text, nullable=True)
    business_profile = db.Column(db.JSON, nullable=True)
    fetched_pages = db.Column(db.JSON, nullable=True)
    screenshots = db.Column(db.JSON, nullable=True)

    sequence_id = db.Column(db.Integer, db.ForeignKey("cro_nurture_sequence.id"), nullable=False, index=True)
    next_step_order = db.Column(db.Integer, nullable=False, default=1)
    next_send_at = db.Column(db.DateTime, nullable=True, index=True)

    unsubscribed_at = db.Column(db.DateTime, nullable=True)
    paused = db.Column(db.Boolean, nullable=False, default=False)
    last_enriched_at = db.Column(db.DateTime, nullable=True)

    source_tag = db.Column(db.String(120), nullable=True)

    sequence = relationship("CroNurtureSequence", back_populates="leads")
    email_sends = relationship("CroNurtureEmailSend", back_populates="lead", cascade="all, delete-orphan")


class CroNurtureEmailSend(db.Model):
    __tablename__ = "cro_nurture_email_send"
    __table_args__ = (UniqueConstraint("lead_id", "sequence_step_id", name="uq_cro_nurture_lead_step_send"),)

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("cro_nurture_lead.id"), nullable=False, index=True)
    sequence_step_id = db.Column(db.Integer, db.ForeignKey("cro_nurture_sequence_step.id"), nullable=False, index=True)

    subject = db.Column(db.String(998), nullable=True)
    html_body = db.Column(db.Text, nullable=True)
    text_body = db.Column(db.Text, nullable=True)

    brevo_message_id = db.Column(db.String(255), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="queued")
    sent_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    last_opened_at = db.Column(db.DateTime, nullable=True)
    open_count = db.Column(db.Integer, nullable=False, default=0)
    last_clicked_at = db.Column(db.DateTime, nullable=True)
    click_count = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    lead = relationship("CroNurtureLead", back_populates="email_sends")
    sequence_step = relationship("CroNurtureSequenceStep", back_populates="sends")
