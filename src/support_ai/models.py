from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Channel(StrEnum):
    CHAT = "chat"
    EMAIL = "email"
    WEB = "web"
    MOBILE = "mobile"


class TopicCode(StrEnum):
    NOTIFICATIONS = "notifications"
    SERVICE_STATUS = "service_status"
    TECHNICAL_ISSUE = "technical_issue"
    GENERAL = "general"
    PAYMENTS = "payments"
    ACCOUNT_SECURITY = "account_security"
    LEGAL = "legal"
    SAFETY = "safety"


class Action(StrEnum):
    HUMAN_REVIEW = "HUMAN_REVIEW"
    AI_PENDING = "AI_PENDING"
    AUTO_REPLY_READY = "AUTO_REPLY_READY"


class RiskLevel(StrEnum):
    LOW = "low"
    HIGH = "high"
    UNKNOWN = "unknown"


class ReasonCode(StrEnum):
    HIGH_RISK_TOPIC = "HIGH_RISK_TOPIC"
    RISK_KEYWORD = "RISK_KEYWORD"
    HIGH_SENSITIVITY_PII = "HIGH_SENSITIVITY_PII"
    RESIDUAL_PII = "RESIDUAL_PII"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    TOPIC_CONFLICT = "TOPIC_CONFLICT"
    SAFE_CONFIDENT = "SAFE_CONFIDENT"
    RETRIEVAL_LOW_CONFIDENCE = "RETRIEVAL_LOW_CONFIDENCE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    RESPONSE_VALIDATION_FAILED = "RESPONSE_VALIDATION_FAILED"
    GENERATION_SUCCEEDED = "GENERATION_SUCCEEDED"


class Message(ContractModel):
    author: Literal["customer", "support"] = "customer"
    text: str = Field(min_length=1, max_length=10_000)


class Ticket(ContractModel):
    event_id: str = Field(min_length=1, max_length=128)
    ticket_id: str = Field(min_length=1, max_length=128)
    channel: Channel
    created_at: datetime
    selected_topic: TopicCode | None = None
    messages: list[Message] = Field(min_length=1, max_length=100)
    customer_ref: str | None = Field(default=None, max_length=128)
    locale: str = Field(default="ru-RU", min_length=2, max_length=16)
    attachment_refs: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: Literal["1.0"] = "1.0"

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def must_contain_customer_message(self) -> Ticket:
        if not any(message.author == "customer" for message in self.messages):
            raise ValueError("ticket must contain at least one customer message")
        return self

    def customer_text(self) -> str:
        return "\n".join(
            message.text for message in self.messages if message.author == "customer"
        )


class SanitizationResult(ContractModel):
    text: str
    redacted_types: list[str] = Field(default_factory=list)
    high_sensitivity_detected: bool = False
    residual_pii_score: float = Field(ge=0.0, le=1.0)


class TopicPrediction(ContractModel):
    topic_code: TopicCode
    rank: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)


class RiskAssessment(ContractModel):
    risk_level: RiskLevel
    reason_code: ReasonCode | None = None
    topic_code: TopicCode | None = None


class GenerationJob(ContractModel):
    job_id: str
    run_id: str
    ticket_id: str
    sanitized_text: str
    predictions: list[TopicPrediction]
    attempt: int = Field(default=1, ge=1)


class FastDecision(ContractModel):
    run_id: str
    ticket_id: str
    action: Action
    reason_code: ReasonCode
    risk_level: RiskLevel
    predictions: list[TopicPrediction] = Field(default_factory=list)
    generation_job: GenerationJob | None = None
    response_ref: str | None = None
    replayed: bool = False


class KnowledgeArticle(ContractModel):
    article_id: str
    version: int = Field(ge=1)
    topic_code: TopicCode
    title: str
    content: str
    status: Literal["active", "retired"]


class RetrievedArticle(KnowledgeArticle):
    rank: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)


class GenerationOutput(ContractModel):
    answer: str = Field(min_length=1, max_length=4_000)
    used_article_ids: list[str] = Field(min_length=1)


class HelpdeskResponse(ContractModel):
    answer: str
    used_article_ids: list[str]


class TicketOutcome(ContractModel):
    run_id: str
    ticket_id: str
    action: Action
    reason_code: ReasonCode
    risk_level: RiskLevel
    topic_code: TopicCode | None = None
    route: str | None = None
    response: HelpdeskResponse | None = None
    response_ref: str | None = None
    replayed: bool = False


class VersionBundle(ContractModel):
    policy_version: str
    pii_rules_version: str
    pii_model_version: str
    classifier_version: str
    retrieval_version: str
    prompt_version: str
    llm_model: str


class AuditDecision(ContractModel):
    decision_id: str
    run_id: str
    stage: str
    action: Action
    reason_code: ReasonCode
    attempt: int
    response_ref: str | None
    created_at: datetime
