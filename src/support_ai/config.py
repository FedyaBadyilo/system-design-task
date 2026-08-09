from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_db_path: Path = Path(".data/audit.db")
    knowledge_base_path: Path = Path("data/knowledge_articles.json")
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    llm_max_completion_tokens: int = Field(default=384, ge=64, le=2_000)
    force_deterministic: bool = False

    @model_validator(mode="after")
    def llm_settings_must_be_complete(self) -> AppConfig:
        configured = [
            bool(self.llm_base_url),
            self.llm_api_key is not None and bool(self.llm_api_key.get_secret_value()),
            bool(self.llm_model),
        ]
        if any(configured) and not all(configured):
            raise ValueError(
                "LLM_BASE_URL, LLM_API_KEY and LLM_MODEL must be set together"
            )
        return self

    @property
    def use_real_llm(self) -> bool:
        return (
            not self.force_deterministic
            and self.llm_base_url is not None
            and self.llm_api_key is not None
            and self.llm_model is not None
        )

    @classmethod
    def from_env(
        cls,
        *,
        force_deterministic: bool = False,
        audit_db_path: Path | None = None,
    ) -> AppConfig:
        load_dotenv()

        def optional_env(name: str) -> str | None:
            value = os.getenv(name, "").strip()
            return value or None

        return cls(
            audit_db_path=audit_db_path
            or Path(os.getenv("AUDIT_DB_PATH", ".data/audit.db")),
            knowledge_base_path=Path(
                os.getenv("KNOWLEDGE_BASE_PATH", "data/knowledge_articles.json")
            ),
            llm_base_url=optional_env("LLM_BASE_URL"),
            llm_api_key=optional_env("LLM_API_KEY"),
            llm_model=optional_env("LLM_MODEL"),
            force_deterministic=force_deterministic,
        )
