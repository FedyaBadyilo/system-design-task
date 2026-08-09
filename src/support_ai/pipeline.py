from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from support_ai.audit import AuditRepository
from support_ai.config import AppConfig
from support_ai.fast_path import (
    CLASSIFIER_VERSION,
    PII_RULES_VERSION,
    POLICY_VERSION,
    assess_risk,
    classification_abstention_reason,
    classify_topics,
    sanitize_text,
)
from support_ai.generation import (
    PROMPT_VERSION,
    DeterministicGenerator,
    GenerationResponseInvalid,
    GenerationUnavailable,
    Generator,
    OpenAICompatibleGenerator,
    validate_generation_output,
)
from support_ai.models import (
    Action,
    FastDecision,
    GenerationJob,
    HelpdeskResponse,
    ReasonCode,
    RiskLevel,
    Ticket,
    TicketOutcome,
    TopicCode,
    TopicPrediction,
    VersionBundle,
)
from support_ai.retrieval import RETRIEVAL_VERSION, KnowledgeBase

TraceSink = Callable[[str, str], None]


class TicketPipeline:
    def __init__(
        self,
        *,
        audit: AuditRepository,
        knowledge_base: KnowledgeBase,
        generator: Generator,
        trace: TraceSink | None = None,
    ) -> None:
        self.audit = audit
        self.knowledge_base = knowledge_base
        self.generator = generator
        self._trace = trace or (lambda stage, message: None)
        self.audit.seed_knowledge_articles(knowledge_base.articles)

    def make_fast_decision(self, ticket: Ticket) -> FastDecision:
        sanitization = sanitize_text(ticket.customer_text())
        if sanitization.redacted_types:
            self._trace(
                "PII",
                "заменены: " + ", ".join(sanitization.redacted_types),
            )
        else:
            self._trace("PII", "формализованные PII не обнаружены")
        versions = VersionBundle(
            policy_version=POLICY_VERSION,
            pii_rules_version=PII_RULES_VERSION,
            pii_model_version="none-poc",
            classifier_version=CLASSIFIER_VERSION,
            retrieval_version=RETRIEVAL_VERSION,
            prompt_version=PROMPT_VERSION,
            llm_model=self.generator.model_name,
        )
        run_id, created = self.audit.start_run(
            event_id=ticket.event_id,
            ticket_id=ticket.ticket_id,
            input_hash=self.audit.input_hash(ticket.model_dump_json()),
            residual_pii_score=sanitization.residual_pii_score,
            versions=versions,
        )
        if not created:
            self._trace("IDEMPOTENCY", "событие уже обработано, новый run не создан")
            return self._replay_fast_decision(ticket.event_id)
        self._trace("AUDIT", f"создан processing run {run_id}")

        risk = assess_risk(
            sanitization.text,
            selected_topic=ticket.selected_topic,
            high_sensitivity_detected=sanitization.high_sensitivity_detected,
            residual_pii_score=sanitization.residual_pii_score,
        )
        if risk.risk_level is RiskLevel.HIGH:
            self._trace(
                "POLICY",
                f"высокий риск: {risk.reason_code.value if risk.reason_code else 'unknown'}",
            )
            predictions = _risk_predictions(risk.topic_code)
            self.audit.add_predictions(run_id, predictions)
            reason_code = risk.reason_code or ReasonCode.RISK_KEYWORD
            self.audit.append_decision(
                run_id=run_id,
                stage="fast_path",
                action=Action.HUMAN_REVIEW,
                reason_code=reason_code,
            )
            self._trace(
                "DECISION",
                f"{Action.HUMAN_REVIEW.value}; retrieval и генерация не запускались",
            )
            return FastDecision(
                run_id=run_id,
                ticket_id=ticket.ticket_id,
                action=Action.HUMAN_REVIEW,
                reason_code=reason_code,
                risk_level=RiskLevel.HIGH,
                predictions=predictions,
            )

        self._trace("POLICY", "рискованные правила не сработали")
        predictions = classify_topics(sanitization.text)
        top_prediction = predictions[0]
        self._trace(
            "CLASSIFIER",
            f"{top_prediction.topic_code.value}, confidence={top_prediction.confidence:.2f}",
        )
        self.audit.add_predictions(run_id, predictions)
        abstention_reason = classification_abstention_reason(
            predictions,
            selected_topic=ticket.selected_topic,
        )
        if abstention_reason is not None:
            self.audit.append_decision(
                run_id=run_id,
                stage="fast_path",
                action=Action.HUMAN_REVIEW,
                reason_code=abstention_reason,
            )
            self._trace(
                "DECISION",
                f"{Action.HUMAN_REVIEW.value}: {abstention_reason.value}; "
                "retrieval и генерация не запускались",
            )
            return FastDecision(
                run_id=run_id,
                ticket_id=ticket.ticket_id,
                action=Action.HUMAN_REVIEW,
                reason_code=abstention_reason,
                risk_level=RiskLevel.UNKNOWN,
                predictions=predictions,
            )

        generation_job = GenerationJob(
            job_id=str(uuid4()),
            run_id=run_id,
            ticket_id=ticket.ticket_id,
            sanitized_text=sanitization.text,
            predictions=predictions,
        )
        self.audit.append_decision(
            run_id=run_id,
            stage="fast_path",
            action=Action.AI_PENDING,
            reason_code=ReasonCode.SAFE_CONFIDENT,
        )
        self._trace("DECISION", Action.AI_PENDING.value)
        return FastDecision(
            run_id=run_id,
            ticket_id=ticket.ticket_id,
            action=Action.AI_PENDING,
            reason_code=ReasonCode.SAFE_CONFIDENT,
            risk_level=RiskLevel.LOW,
            predictions=predictions,
            generation_job=generation_job,
        )

    def process_generation_job(self, job: GenerationJob) -> TicketOutcome:
        articles = self.knowledge_base.retrieve(
            job.sanitized_text,
            job.predictions,
        )
        topic_code = job.predictions[0].topic_code if job.predictions else None
        if not articles:
            self._trace("RETRIEVAL", "подходящие статьи выше порога не найдены")
            self.audit.append_decision(
                run_id=job.run_id,
                stage="generation",
                action=Action.HUMAN_REVIEW,
                reason_code=ReasonCode.RETRIEVAL_LOW_CONFIDENCE,
                attempt=job.attempt,
            )
            self._trace(
                "DECISION",
                f"{Action.HUMAN_REVIEW.value}: "
                f"{ReasonCode.RETRIEVAL_LOW_CONFIDENCE.value}",
            )
            return _human_outcome(
                run_id=job.run_id,
                ticket_id=job.ticket_id,
                reason_code=ReasonCode.RETRIEVAL_LOW_CONFIDENCE,
                risk_level=RiskLevel.UNKNOWN,
                topic_code=topic_code,
            )

        self._trace(
            "RETRIEVAL",
            ", ".join(
                f"{article.article_id} score={article.score:.3f}"
                for article in articles
            ),
        )
        self._trace("GENERATION", f"вызов {self.generator.model_name}")
        try:
            output = self.generator.generate(job.sanitized_text, articles)
            validate_generation_output(output, articles)
        except GenerationUnavailable:
            self._trace("GENERATION", "зависимость недоступна")
            self.audit.append_decision(
                run_id=job.run_id,
                stage="generation",
                action=Action.HUMAN_REVIEW,
                reason_code=ReasonCode.DEPENDENCY_FAILURE,
                attempt=job.attempt,
            )
            self._trace(
                "DECISION",
                f"{Action.HUMAN_REVIEW.value}: {ReasonCode.DEPENDENCY_FAILURE.value}",
            )
            return _human_outcome(
                run_id=job.run_id,
                ticket_id=job.ticket_id,
                reason_code=ReasonCode.DEPENDENCY_FAILURE,
                risk_level=RiskLevel.LOW,
                topic_code=topic_code,
            )
        except GenerationResponseInvalid:
            self._trace("GENERATION", "ответ не прошёл детерминированные проверки")
            self.audit.append_decision(
                run_id=job.run_id,
                stage="generation",
                action=Action.HUMAN_REVIEW,
                reason_code=ReasonCode.RESPONSE_VALIDATION_FAILED,
                attempt=job.attempt,
            )
            self._trace(
                "DECISION",
                f"{Action.HUMAN_REVIEW.value}: "
                f"{ReasonCode.RESPONSE_VALIDATION_FAILED.value}",
            )
            return _human_outcome(
                run_id=job.run_id,
                ticket_id=job.ticket_id,
                reason_code=ReasonCode.RESPONSE_VALIDATION_FAILED,
                risk_level=RiskLevel.UNKNOWN,
                topic_code=topic_code,
            )

        self._trace(
            "GENERATION",
            "ответ получен; JSON schema, citations и PII-проверки пройдены",
        )
        response_ref = (
            f"poc://helpdesk/tickets/{job.ticket_id}/responses/{uuid4()}"
        )
        decision = self.audit.append_decision(
            run_id=job.run_id,
            stage="generation",
            action=Action.AUTO_REPLY_READY,
            reason_code=ReasonCode.GENERATION_SUCCEEDED,
            attempt=job.attempt,
            response_ref=response_ref,
        )
        used_ids = set(output.used_article_ids)
        self.audit.add_evidence(
            decision.decision_id,
            [article for article in articles if article.article_id in used_ids],
        )
        self._trace("DECISION", Action.AUTO_REPLY_READY.value)
        return TicketOutcome(
            run_id=job.run_id,
            ticket_id=job.ticket_id,
            action=Action.AUTO_REPLY_READY,
            reason_code=ReasonCode.GENERATION_SUCCEEDED,
            risk_level=RiskLevel.LOW,
            topic_code=topic_code,
            response=HelpdeskResponse(
                answer=output.answer,
                used_article_ids=output.used_article_ids,
            ),
            response_ref=response_ref,
        )

    def process_ticket(self, ticket: Ticket) -> TicketOutcome:
        fast_decision = self.make_fast_decision(ticket)
        if fast_decision.replayed:
            return TicketOutcome(
                run_id=fast_decision.run_id,
                ticket_id=fast_decision.ticket_id,
                action=fast_decision.action,
                reason_code=fast_decision.reason_code,
                risk_level=fast_decision.risk_level,
                topic_code=_top_topic(fast_decision.predictions),
                route=(
                    _route_for_topic(_top_topic(fast_decision.predictions))
                    if fast_decision.action is Action.HUMAN_REVIEW
                    else None
                ),
                response_ref=fast_decision.response_ref,
                replayed=True,
            )
        if fast_decision.action is Action.HUMAN_REVIEW:
            return _human_outcome(
                run_id=fast_decision.run_id,
                ticket_id=fast_decision.ticket_id,
                reason_code=fast_decision.reason_code,
                risk_level=fast_decision.risk_level,
                topic_code=_top_topic(fast_decision.predictions),
            )
        if fast_decision.generation_job is None:
            raise RuntimeError("AI_PENDING decision has no generation job")
        return self.process_generation_job(fast_decision.generation_job)

    def _replay_fast_decision(self, event_id: str) -> FastDecision:
        existing = self.audit.latest_decision_for_event(event_id)
        if existing is None:
            raise RuntimeError("idempotent run has no audit decision")
        decision, _, ticket_id = existing
        predictions = self.audit.predictions_for_run(decision.run_id)
        return FastDecision(
            run_id=decision.run_id,
            ticket_id=ticket_id,
            action=decision.action,
            reason_code=decision.reason_code,
            risk_level=_risk_level_for_reason(decision.reason_code),
            predictions=predictions,
            response_ref=decision.response_ref,
            replayed=True,
        )


def build_pipeline(
    config: AppConfig,
    *,
    generator: Generator | None = None,
    trace: TraceSink | None = None,
) -> TicketPipeline:
    selected_generator = generator or _generator_from_config(config)
    return TicketPipeline(
        audit=AuditRepository(config.audit_db_path),
        knowledge_base=KnowledgeBase.from_json(config.knowledge_base_path),
        generator=selected_generator,
        trace=trace,
    )


def _generator_from_config(config: AppConfig) -> Generator:
    if not config.use_real_llm:
        return DeterministicGenerator()
    if (
        config.llm_base_url is None
        or config.llm_api_key is None
        or config.llm_model is None
    ):
        raise RuntimeError("validated LLM configuration is incomplete")
    return OpenAICompatibleGenerator(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key.get_secret_value(),
        model=config.llm_model,
        timeout_seconds=config.llm_timeout_seconds,
        max_completion_tokens=config.llm_max_completion_tokens,
    )


def _risk_predictions(topic_code: TopicCode | None) -> list[TopicPrediction]:
    if topic_code is None:
        return []
    return [TopicPrediction(topic_code=topic_code, rank=1, confidence=0.99)]


def _top_topic(predictions: list[TopicPrediction]) -> TopicCode | None:
    return predictions[0].topic_code if predictions else None


def _human_outcome(
    *,
    run_id: str,
    ticket_id: str,
    reason_code: ReasonCode,
    risk_level: RiskLevel,
    topic_code: TopicCode | None,
) -> TicketOutcome:
    return TicketOutcome(
        run_id=run_id,
        ticket_id=ticket_id,
        action=Action.HUMAN_REVIEW,
        reason_code=reason_code,
        risk_level=risk_level,
        topic_code=topic_code,
        route=_route_for_topic(topic_code),
    )


def _route_for_topic(topic_code: TopicCode | None) -> str:
    routes = {
        TopicCode.PAYMENTS: "payments-specialists",
        TopicCode.ACCOUNT_SECURITY: "account-security-specialists",
        TopicCode.LEGAL: "legal-and-safety",
        TopicCode.SAFETY: "legal-and-safety",
    }
    return routes.get(topic_code, "general-human-review")


def _risk_level_for_reason(reason_code: ReasonCode) -> RiskLevel:
    if reason_code in {
        ReasonCode.HIGH_RISK_TOPIC,
        ReasonCode.RISK_KEYWORD,
        ReasonCode.HIGH_SENSITIVITY_PII,
        ReasonCode.RESIDUAL_PII,
    }:
        return RiskLevel.HIGH
    if reason_code in {
        ReasonCode.SAFE_CONFIDENT,
        ReasonCode.GENERATION_SUCCEEDED,
        ReasonCode.DEPENDENCY_FAILURE,
    }:
        return RiskLevel.LOW
    return RiskLevel.UNKNOWN
