from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from support_ai.config import AppConfig
from support_ai.generation import FailingGenerator, Generator
from support_ai.models import (
    Action,
    Channel,
    GenerationOutput,
    Message,
    ReasonCode,
    RetrievedArticle,
    Ticket,
    TopicCode,
)
from support_ai.pipeline import TraceSink, TicketPipeline, build_pipeline

KNOWLEDGE_BASE_PATH = Path("data/knowledge_articles.json")


class CapturingGenerator:
    model_name = "capturing-generator"

    def __init__(self) -> None:
        self.received_texts: list[str] = []

    def generate(
        self, sanitized_text: str, articles: list[RetrievedArticle]
    ) -> GenerationOutput:
        self.received_texts.append(sanitized_text)
        return GenerationOutput(
            answer="Включите уведомления в профиле и настройках устройства.",
            used_article_ids=[articles[0].article_id],
        )


class UnexpectedGenerator:
    model_name = "must-not-be-called"

    def generate(
        self, sanitized_text: str, articles: list[RetrievedArticle]
    ) -> GenerationOutput:
        del sanitized_text, articles
        raise AssertionError("generator must not be called")


def test_happy_path_redacts_pii_retrieves_and_audits(tmp_path: Path) -> None:
    generator = CapturingGenerator()
    traced_stages: list[str] = []
    pipeline = _pipeline(
        tmp_path,
        generator,
        trace=lambda stage, message: traced_stages.append(stage),
    )
    ticket = _ticket(
        event_id="event-happy",
        text=(
            "Не приходят уведомления о сообщениях на private.user@example.com. "
            "Как их включить?"
        ),
    )

    outcome = pipeline.process_ticket(ticket)

    assert outcome.action is Action.AUTO_REPLY_READY
    assert outcome.topic_code is TopicCode.NOTIFICATIONS
    assert outcome.response is not None
    assert outcome.response.used_article_ids == ["kb-notifications-001"]
    assert generator.received_texts == [
        "Не приходят уведомления о сообщениях на [EMAIL]. Как их включить?"
    ]

    db_path = tmp_path / "audit.db"
    with sqlite3.connect(db_path) as connection:
        actions = connection.execute(
            "SELECT action FROM decision ORDER BY created_at"
        ).fetchall()
        evidence_count = connection.execute(
            "SELECT COUNT(*) FROM decision_evidence"
        ).fetchone()[0]
    assert actions == [("AI_PENDING",), ("AUTO_REPLY_READY",)]
    assert evidence_count == 1
    assert b"private.user@example.com" not in db_path.read_bytes()
    assert "RETRIEVAL" in traced_stages
    assert "GENERATION" in traced_stages


@pytest.mark.parametrize(
    ("event_id", "text", "selected_topic", "expected_reason"),
    [
        (
            "event-risky",
            "С карты дважды списали деньги, нужен возврат.",
            TopicCode.PAYMENTS,
            ReasonCode.HIGH_RISK_TOPIC,
        ),
        (
            "event-uncertain",
            "У меня нестандартный вопрос, помогите.",
            None,
            ReasonCode.LOW_CONFIDENCE,
        ),
    ],
)
def test_risky_or_uncertain_ticket_never_calls_generator(
    tmp_path: Path,
    event_id: str,
    text: str,
    selected_topic: TopicCode | None,
    expected_reason: ReasonCode,
) -> None:
    traced_stages: list[str] = []
    pipeline = _pipeline(
        tmp_path,
        UnexpectedGenerator(),
        trace=lambda stage, message: traced_stages.append(stage),
    )
    ticket = _ticket(
        event_id=event_id,
        text=text,
        selected_topic=selected_topic,
    )

    outcome = pipeline.process_ticket(ticket)

    assert outcome.action is Action.HUMAN_REVIEW
    assert outcome.reason_code is expected_reason
    assert outcome.response is None
    assert outcome.route is not None
    assert "RETRIEVAL" not in traced_stages
    assert "GENERATION" not in traced_stages


def test_generation_failure_gracefully_routes_to_human(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path, FailingGenerator())

    outcome = pipeline.process_ticket(
        _ticket(
            event_id="event-llm-failure",
            text="Не приходят push-уведомления. Как их включить?",
        )
    )

    assert outcome.action is Action.HUMAN_REVIEW
    assert outcome.reason_code is ReasonCode.DEPENDENCY_FAILURE
    assert outcome.response is None


def test_repeated_event_is_idempotent(tmp_path: Path) -> None:
    generator = CapturingGenerator()
    pipeline = _pipeline(tmp_path, generator)
    ticket = _ticket(
        event_id="event-duplicate",
        text="Не приходят уведомления о новых сообщениях. Как их включить?",
    )

    first = pipeline.process_ticket(ticket)
    second = pipeline.process_ticket(ticket)

    assert first.run_id == second.run_id
    assert first.response_ref == second.response_ref
    assert second.replayed is True
    assert len(generator.received_texts) == 1
    assert pipeline.audit.count_runs_for_event(ticket.event_id) == 1


def test_ticket_contract_rejects_naive_datetime_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Ticket.model_validate(
            {
                "event_id": "event-invalid",
                "ticket_id": "ticket-invalid",
                "channel": "chat",
                "created_at": "2026-08-09T12:00:00",
                "messages": [{"text": "Сообщение"}],
                "unexpected": True,
            }
        )


def _pipeline(
    tmp_path: Path,
    generator: Generator,
    *,
    trace: TraceSink | None = None,
) -> TicketPipeline:
    config = AppConfig(
        audit_db_path=tmp_path / "audit.db",
        knowledge_base_path=KNOWLEDGE_BASE_PATH,
        force_deterministic=True,
    )
    return build_pipeline(config, generator=generator, trace=trace)


def _ticket(
    *,
    event_id: str,
    text: str,
    selected_topic: TopicCode | None = None,
) -> Ticket:
    return Ticket(
        event_id=event_id,
        ticket_id=f"ticket-{event_id}",
        channel=Channel.CHAT,
        created_at=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
        selected_topic=selected_topic,
        messages=[Message(text=text)],
    )
