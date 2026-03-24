from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid


class ProspectEvent(BaseModel):
    event_type: Literal["new_lead", "email_open", "demo_request", "doc_upload", "job_change"]
    prospect_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    contact_name: str
    email: str
    company_size: Optional[str] = None
    industry: Optional[str] = None
    revenue: Optional[str] = None
    tech_stack: Optional[list[str]] = None
    geography: Optional[str] = None
    linkedin_url: Optional[str] = None
    metadata: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SignalData(BaseModel):
    firmographic: Optional[dict] = None
    intent: Optional[dict] = None
    engagement: Optional[dict] = None
    social: Optional[dict] = None
    historical: Optional[dict] = None


class ProspectScore(BaseModel):
    prospect_id: str
    company_name: str
    contact_name: str
    email: str
    score: float = Field(ge=0, le=100)
    grade: Literal["A", "B", "C", "D"]
    rationale: str
    recommended_action: str
    signals: SignalData
    rag_context: Optional[str] = None
    requires_human_review: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackPayload(BaseModel):
    prospect_id: str
    outcome: Literal["won", "lost", "ghosted", "nurturing"]
    notes: Optional[str] = None


class DocumentUpload(BaseModel):
    prospect_id: str
    doc_type: Literal["text", "image", "pdf", "mixed"]
    filename: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None


class HumanReviewDecision(BaseModel):
    prospect_id: str
    approved: bool
    reviewer_notes: Optional[str] = None
    override_action: Optional[str] = None
