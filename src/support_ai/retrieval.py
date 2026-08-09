from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from support_ai.models import (
    KnowledgeArticle,
    RetrievedArticle,
    TopicPrediction,
)

RETRIEVAL_VERSION = "tfidf-v1"
MIN_RETRIEVAL_SCORE = 0.08


class KnowledgeBase:
    def __init__(self, articles: list[KnowledgeArticle]) -> None:
        self.articles = articles

    @classmethod
    def from_json(cls, path: Path) -> KnowledgeBase:
        with path.open(encoding="utf-8") as source:
            raw_articles = json.load(source)
        articles = TypeAdapter(list[KnowledgeArticle]).validate_python(raw_articles)
        return cls(articles)

    def retrieve(
        self,
        sanitized_text: str,
        predictions: list[TopicPrediction],
        *,
        top_k: int = 3,
        min_score: float = MIN_RETRIEVAL_SCORE,
    ) -> list[RetrievedArticle]:
        candidate_topics = {prediction.topic_code for prediction in predictions}
        candidates = [
            article
            for article in self.articles
            if article.status == "active" and article.topic_code in candidate_topics
        ]
        if not candidates:
            return []

        documents = [
            f"{article.title}. {article.content}" for article in candidates
        ]
        matrix = TfidfVectorizer(ngram_range=(1, 2)).fit_transform(
            [*documents, sanitized_text]
        )
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        ranked = sorted(
            zip(candidates, scores, strict=True),
            key=lambda item: (-float(item[1]), item[0].article_id),
        )

        results: list[RetrievedArticle] = []
        for article, score in ranked:
            numeric_score = float(score)
            if numeric_score < min_score:
                continue
            results.append(
                RetrievedArticle(
                    **article.model_dump(),
                    rank=len(results) + 1,
                    score=numeric_score,
                )
            )
            if len(results) == top_k:
                break
        return results
