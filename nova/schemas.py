from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Approval(StrictModel):
    version: int = Field(ge=1)


class ImportApproval(StrictModel):
    contacts: dict[str, EmailStr] = Field(default_factory=dict)


class ContactApproval(StrictModel):
    revision: int = Field(ge=1)
    recipient: EmailStr


class DraftEdit(Approval):
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=50000)


class ProposalEdit(Approval):
    value: str = Field(min_length=1, max_length=10000)


class SendReconciliation(Approval):
    outcome: Literal["sent", "not_sent"]
    note: str = Field(min_length=5, max_length=2000)
    provider_id: str | None = Field(default=None, max_length=500)
    sent_at: datetime | None = None


class Evidence(StrictModel):
    source_id: str
    quote: str = Field(min_length=1)


class Candidate(StrictModel):
    field_id: str
    value: str = Field(min_length=1, max_length=10000)
    evidence: Evidence
    rationale: str


class Evaluation(StrictModel):
    candidates: list[Candidate]
