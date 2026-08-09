from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from support_ai.config import AppConfig
from support_ai.generation import FailingGenerator
from support_ai.models import Channel, Message, Ticket, TicketOutcome, TopicCode
from support_ai.pipeline import build_pipeline

_SCENARIO_TITLES = {
    "happy": "Безопасный типовой запрос",
    "risky": "Рискованный платёжный запрос",
    "low-confidence": "Запрос с низкой уверенностью",
    "llm-unavailable": "Недоступность генерации",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run minimal support-ticket automation scenarios."
    )
    parser.add_argument(
        "--scenario",
        choices=("all", "happy", "risky", "low-confidence", "llm-unavailable"),
        help="Run a predefined scenario; defaults to all when --text is absent.",
    )
    parser.add_argument(
        "--text",
        help="Process one custom synthetic request instead of predefined scenarios.",
    )
    parser.add_argument(
        "--channel",
        choices=tuple(channel.value for channel in Channel),
        default=Channel.CHAT.value,
        help="Channel for --text.",
    )
    parser.add_argument(
        "--selected-topic",
        choices=tuple(topic.value for topic in TopicCode),
        help="Optional user-selected topic for --text.",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Use the deterministic generator even when LLM env vars are set.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Override the SQLite audit path.",
    )
    args = parser.parse_args()
    if args.text and args.scenario:
        parser.error("--text and --scenario cannot be used together")
    if args.selected_topic and not args.text:
        parser.error("--selected-topic requires --text")

    config = AppConfig.from_env(
        force_deterministic=args.deterministic,
        audit_db_path=args.db_path,
    )
    if args.text:
        runs = [
            (
                "Собственный запрос",
                _custom_ticket(
                    text=args.text,
                    channel=Channel(args.channel),
                    selected_topic=(
                        TopicCode(args.selected_topic)
                        if args.selected_topic
                        else None
                    ),
                ),
                False,
            )
        ]
    else:
        scenario = args.scenario or "all"
        runs = [
            (
                _SCENARIO_TITLES[scenario_name],
                _ticket_for_scenario(scenario_name),
                scenario_name == "llm-unavailable",
            )
            for scenario_name in _selected_scenarios(scenario)
        ]

    for title, ticket, simulate_failure in runs:
        generator = (
            FailingGenerator() if simulate_failure else None
        )
        print(f"\n=== {title} ===")
        print(f"Канал: {ticket.channel.value}")
        print(
            "Выбранная тема: "
            f"{ticket.selected_topic.value if ticket.selected_topic else 'не указана'}"
        )
        print(f"Запрос: {ticket.customer_text()}")
        print("Фактически выполненные этапы:")
        pipeline = build_pipeline(
            config,
            generator=generator,
            trace=_print_trace,
        )
        outcome = pipeline.process_ticket(ticket)
        _print_outcome(outcome)
    print(f"\nAudit DB: {config.audit_db_path}")


def _selected_scenarios(scenario: str) -> tuple[str, ...]:
    if scenario == "all":
        return ("happy", "risky", "low-confidence", "llm-unavailable")
    return (scenario,)


def _ticket_for_scenario(scenario: str) -> Ticket:
    suffix = uuid4()
    common = {
        "event_id": f"demo-event-{scenario}-{suffix}",
        "ticket_id": f"demo-ticket-{scenario}-{suffix}",
        "created_at": datetime.now(timezone.utc),
    }
    if scenario == "happy":
        return Ticket(
            **common,
            channel=Channel.CHAT,
            messages=[
                Message(
                    text=(
                        "Не приходят уведомления о новых сообщениях на "
                        "demo@example.invalid. Как их включить?"
                    )
                )
            ],
        )
    if scenario == "risky":
        return Ticket(
            **common,
            channel=Channel.WEB,
            selected_topic=TopicCode.PAYMENTS,
            messages=[
                Message(text="С карты дважды списали деньги, нужен возврат.")
            ],
        )
    if scenario == "low-confidence":
        return Ticket(
            **common,
            channel=Channel.EMAIL,
            messages=[Message(text="У меня нестандартный вопрос, помогите.")],
        )
    if scenario == "llm-unavailable":
        return Ticket(
            **common,
            channel=Channel.MOBILE,
            messages=[
                Message(text="Не приходят push-уведомления. Как их включить?")
            ],
        )
    raise ValueError(f"unknown scenario: {scenario}")


def _custom_ticket(
    *,
    text: str,
    channel: Channel,
    selected_topic: TopicCode | None,
) -> Ticket:
    suffix = uuid4()
    return Ticket(
        event_id=f"custom-event-{suffix}",
        ticket_id=f"custom-ticket-{suffix}",
        channel=channel,
        created_at=datetime.now(timezone.utc),
        selected_topic=selected_topic,
        messages=[Message(text=text)],
    )


def _print_trace(stage: str, message: str) -> None:
    print(f"  [{stage}] {message}")


def _print_outcome(outcome: TicketOutcome) -> None:
    print("Результат:")
    print(f"  Действие: {outcome.action.value}")
    print(f"  Причина: {outcome.reason_code.value}")
    print(
        f"  Тема: {outcome.topic_code.value if outcome.topic_code else 'не определена'}"
    )
    if outcome.route:
        print(f"  Маршрут: {outcome.route}")
    if outcome.response:
        print(f"  Ответ: {outcome.response.answer}")
        print(f"  Источники: {', '.join(outcome.response.used_article_ids)}")
    if outcome.response_ref:
        print(f"  Response ref: {outcome.response_ref}")
    print(f"  Audit run: {outcome.run_id}")


if __name__ == "__main__":
    main()
