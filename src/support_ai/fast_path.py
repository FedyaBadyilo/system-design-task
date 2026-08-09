from __future__ import annotations

import re
from collections.abc import Iterable

from support_ai.models import (
    ReasonCode,
    RiskAssessment,
    RiskLevel,
    SanitizationResult,
    TopicCode,
    TopicPrediction,
)

PII_RULES_VERSION = "regex-v1"
CLASSIFIER_VERSION = "keyword-mock-v1"
POLICY_VERSION = "policy-v1"
MIN_CLASSIFIER_CONFIDENCE = 0.75

_PII_PATTERNS: tuple[tuple[str, re.Pattern[str], str, bool], ...] = (
    (
        "payment_card",
        re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
        "[PAYMENT_CARD]",
        True,
    ),
    (
        "passport",
        re.compile(r"(?<!\d)\d{4}\s?\d{6}(?!\d)"),
        "[PASSPORT]",
        True,
    ),
    (
        "email",
        re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
        "[EMAIL]",
        False,
    ),
    (
        "phone",
        re.compile(
            r"(?<!\d)(?:\+7|8)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)"
        ),
        "[PHONE]",
        False,
    ),
)

_RESIDUAL_PII_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"(?<!\d)\d{9,}(?!\d)"),
)

_RISK_TOPICS = {
    TopicCode.PAYMENTS,
    TopicCode.ACCOUNT_SECURITY,
    TopicCode.LEGAL,
    TopicCode.SAFETY,
}

_RISK_KEYWORDS: tuple[tuple[TopicCode, tuple[str, ...]], ...] = (
    (
        TopicCode.PAYMENTS,
        ("оплат", "платеж", "деньг", "возврат", "списал", "банк", "карт"),
    ),
    (
        TopicCode.ACCOUNT_SECURITY,
        ("взлом", "парол", "аккаунт", "не могу войти", "код подтверждения"),
    ),
    (TopicCode.LEGAL, ("суд", "закон", "юрист", "претензи", "персональн")),
    (TopicCode.SAFETY, ("угроз", "самоуб", "насили", "опасност")),
)

_SAFE_KEYWORDS: dict[TopicCode, tuple[str, ...]] = {
    TopicCode.NOTIFICATIONS: (
        "уведомлен",
        "оповещен",
        "push",
        "пуш",
        "сообщени",
    ),
    TopicCode.SERVICE_STATUS: (
        "недоступ",
        "не работает",
        "сбой",
        "статус",
        "загруз",
    ),
    TopicCode.TECHNICAL_ISSUE: (
        "ошибк",
        "приложени",
        "браузер",
        "кеш",
        "обнов",
    ),
    TopicCode.GENERAL: ("как", "где", "подскаж", "помог"),
}


def sanitize_text(text: str) -> SanitizationResult:
    sanitized = text
    redacted_types: list[str] = []
    high_sensitivity_detected = False

    for pii_type, pattern, placeholder, is_high_sensitivity in _PII_PATTERNS:
        sanitized, substitutions = pattern.subn(placeholder, sanitized)
        if substitutions:
            redacted_types.append(pii_type)
            high_sensitivity_detected = (
                high_sensitivity_detected or is_high_sensitivity
            )

    residual_matches = sum(
        bool(pattern.search(sanitized)) for pattern in _RESIDUAL_PII_PATTERNS
    )
    residual_score = min(1.0, residual_matches * 0.6)
    return SanitizationResult(
        text=sanitized,
        redacted_types=redacted_types,
        high_sensitivity_detected=high_sensitivity_detected,
        residual_pii_score=residual_score,
    )


def contains_pii(text: str) -> bool:
    return any(pattern.search(text) for _, pattern, _, _ in _PII_PATTERNS) or any(
        pattern.search(text) for pattern in _RESIDUAL_PII_PATTERNS
    )


def assess_risk(
    sanitized_text: str,
    *,
    selected_topic: TopicCode | None,
    high_sensitivity_detected: bool,
    residual_pii_score: float,
) -> RiskAssessment:
    if high_sensitivity_detected:
        return RiskAssessment(
            risk_level=RiskLevel.HIGH,
            reason_code=ReasonCode.HIGH_SENSITIVITY_PII,
            topic_code=selected_topic,
        )
    if residual_pii_score > 0:
        return RiskAssessment(
            risk_level=RiskLevel.HIGH,
            reason_code=ReasonCode.RESIDUAL_PII,
            topic_code=selected_topic,
        )
    if selected_topic in _RISK_TOPICS:
        return RiskAssessment(
            risk_level=RiskLevel.HIGH,
            reason_code=ReasonCode.HIGH_RISK_TOPIC,
            topic_code=selected_topic,
        )

    lowered = sanitized_text.casefold()
    for topic_code, keywords in _RISK_KEYWORDS:
        if _contains_any(lowered, keywords):
            return RiskAssessment(
                risk_level=RiskLevel.HIGH,
                reason_code=ReasonCode.RISK_KEYWORD,
                topic_code=topic_code,
            )
    return RiskAssessment(risk_level=RiskLevel.LOW)


def classify_topics(sanitized_text: str, *, top_n: int = 3) -> list[TopicPrediction]:
    lowered = sanitized_text.casefold()
    matched_counts = {
        topic: sum(keyword in lowered for keyword in keywords)
        for topic, keywords in _SAFE_KEYWORDS.items()
    }
    has_specific_signal = any(
        count
        for topic, count in matched_counts.items()
        if topic is not TopicCode.GENERAL
    )

    if has_specific_signal:
        base_scores = {
            TopicCode.NOTIFICATIONS: 0.82,
            TopicCode.SERVICE_STATUS: 0.81,
            TopicCode.TECHNICAL_ISSUE: 0.79,
        }
        scored = [
            (
                topic,
                (
                    min(0.96, base_scores[topic] + 0.05 * count)
                    if count
                    else 0.08
                ),
            )
            for topic, count in matched_counts.items()
            if topic is not TopicCode.GENERAL
        ]
        scored.append((TopicCode.GENERAL, 0.20))
    else:
        scored = [
            (TopicCode.GENERAL, 0.38),
            (TopicCode.TECHNICAL_ISSUE, 0.27),
            (TopicCode.SERVICE_STATUS, 0.20),
            (TopicCode.NOTIFICATIONS, 0.15),
        ]

    ranked = sorted(scored, key=lambda item: (-item[1], item[0].value))[:top_n]
    return [
        TopicPrediction(topic_code=topic, rank=rank, confidence=confidence)
        for rank, (topic, confidence) in enumerate(ranked, start=1)
    ]


def classification_abstention_reason(
    predictions: list[TopicPrediction],
    *,
    selected_topic: TopicCode | None,
) -> ReasonCode | None:
    top_prediction = predictions[0]
    if top_prediction.confidence < MIN_CLASSIFIER_CONFIDENCE:
        return ReasonCode.LOW_CONFIDENCE
    if (
        selected_topic is not None
        and selected_topic is not TopicCode.GENERAL
        and selected_topic is not top_prediction.topic_code
    ):
        return ReasonCode.TOPIC_CONFLICT
    return None


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)
