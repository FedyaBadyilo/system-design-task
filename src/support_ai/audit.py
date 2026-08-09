from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from support_ai.models import (
    Action,
    AuditDecision,
    KnowledgeArticle,
    ReasonCode,
    RetrievedArticle,
    TopicCode,
    TopicPrediction,
    VersionBundle,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS version_bundle (
    version_bundle_id TEXT PRIMARY KEY,
    policy_version TEXT NOT NULL,
    pii_rules_version TEXT NOT NULL,
    pii_model_version TEXT NOT NULL,
    classifier_version TEXT NOT NULL,
    retrieval_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    llm_model TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processing_run (
    run_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    ticket_id TEXT NOT NULL,
    version_bundle_id TEXT NOT NULL REFERENCES version_bundle(version_bundle_id),
    input_hash TEXT NOT NULL,
    residual_pii_score REAL NOT NULL,
    started_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES processing_run(run_id),
    stage TEXT NOT NULL,
    action TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    response_ref TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_prediction (
    run_id TEXT NOT NULL REFERENCES processing_run(run_id),
    topic_code TEXT NOT NULL,
    rank INTEGER NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY (run_id, topic_code)
);

CREATE TABLE IF NOT EXISTS knowledge_article (
    article_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    topic_code TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (article_id, version)
);

CREATE TABLE IF NOT EXISTS decision_evidence (
    decision_id TEXT NOT NULL REFERENCES decision(decision_id),
    article_id TEXT NOT NULL,
    article_version INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL,
    PRIMARY KEY (decision_id, article_id, article_version),
    FOREIGN KEY (article_id, article_version)
        REFERENCES knowledge_article(article_id, version)
);
"""


class AuditRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(_SCHEMA)
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def start_run(
        self,
        *,
        event_id: str,
        ticket_id: str,
        input_hash: str,
        residual_pii_score: float,
        versions: VersionBundle,
    ) -> tuple[str, bool]:
        version_bundle_id = str(
            uuid5(
                NAMESPACE_URL,
                json.dumps(versions.model_dump(), sort_keys=True),
            )
        )
        run_id = str(uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO version_bundle (
                    version_bundle_id, policy_version, pii_rules_version,
                    pii_model_version, classifier_version, retrieval_version,
                    prompt_version, llm_model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_bundle_id,
                    versions.policy_version,
                    versions.pii_rules_version,
                    versions.pii_model_version,
                    versions.classifier_version,
                    versions.retrieval_version,
                    versions.prompt_version,
                    versions.llm_model,
                ),
            )
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO processing_run (
                    run_id, event_id, ticket_id, version_bundle_id, input_hash,
                    residual_pii_score, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_id,
                    ticket_id,
                    version_bundle_id,
                    input_hash,
                    residual_pii_score,
                    started_at,
                ),
            )
            created = cursor.rowcount == 1
            if not created:
                row = connection.execute(
                    "SELECT run_id FROM processing_run WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("idempotency lookup failed")
                run_id = str(row["run_id"])
            connection.commit()
        return run_id, created

    def add_predictions(
        self, run_id: str, predictions: list[TopicPrediction]
    ) -> None:
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO topic_prediction (
                    run_id, topic_code, rank, confidence
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        prediction.topic_code.value,
                        prediction.rank,
                        prediction.confidence,
                    )
                    for prediction in predictions
                ],
            )
            connection.commit()

    def append_decision(
        self,
        *,
        run_id: str,
        stage: str,
        action: Action,
        reason_code: ReasonCode,
        attempt: int = 1,
        response_ref: str | None = None,
    ) -> AuditDecision:
        decision = AuditDecision(
            decision_id=str(uuid4()),
            run_id=run_id,
            stage=stage,
            action=action,
            reason_code=reason_code,
            attempt=attempt,
            response_ref=response_ref,
            created_at=datetime.now(timezone.utc),
        )
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO decision (
                    decision_id, run_id, stage, action, reason_code, attempt,
                    response_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.run_id,
                    decision.stage,
                    decision.action.value,
                    decision.reason_code.value,
                    decision.attempt,
                    decision.response_ref,
                    decision.created_at.isoformat(),
                ),
            )
            connection.commit()
        return decision

    def add_evidence(
        self, decision_id: str, articles: list[RetrievedArticle]
    ) -> None:
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO decision_evidence (
                    decision_id, article_id, article_version, rank, score
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        decision_id,
                        article.article_id,
                        article.version,
                        article.rank,
                        article.score,
                    )
                    for article in articles
                ],
            )
            connection.commit()

    def seed_knowledge_articles(self, articles: list[KnowledgeArticle]) -> None:
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO knowledge_article (
                    article_id, version, topic_code, title, content, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        article.article_id,
                        article.version,
                        article.topic_code.value,
                        article.title,
                        article.content,
                        article.status,
                    )
                    for article in articles
                ],
            )
            connection.commit()

    def latest_decision_for_event(
        self, event_id: str
    ) -> tuple[AuditDecision, TopicCode | None, str] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT d.*, p.ticket_id
                FROM decision AS d
                JOIN processing_run AS p ON p.run_id = d.run_id
                WHERE p.event_id = ?
                ORDER BY d.created_at DESC
                LIMIT 1
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            prediction_row = connection.execute(
                """
                SELECT topic_code
                FROM topic_prediction
                WHERE run_id = ?
                ORDER BY rank
                LIMIT 1
                """,
                (row["run_id"],),
            ).fetchone()

        decision = AuditDecision(
            decision_id=row["decision_id"],
            run_id=row["run_id"],
            stage=row["stage"],
            action=Action(row["action"]),
            reason_code=ReasonCode(row["reason_code"]),
            attempt=row["attempt"],
            response_ref=row["response_ref"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        topic_code = (
            TopicCode(prediction_row["topic_code"])
            if prediction_row is not None
            else None
        )
        return decision, topic_code, str(row["ticket_id"])

    def predictions_for_run(self, run_id: str) -> list[TopicPrediction]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT topic_code, rank, confidence
                FROM topic_prediction
                WHERE run_id = ?
                ORDER BY rank
                """,
                (run_id,),
            ).fetchall()
        return [
            TopicPrediction(
                topic_code=TopicCode(row["topic_code"]),
                rank=row["rank"],
                confidence=row["confidence"],
            )
            for row in rows
        ]

    def count_runs_for_event(self, event_id: str) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM processing_run WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def input_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
