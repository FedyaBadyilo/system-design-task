---
name: minimal-poc
overview: "Реализовать локальный Python PoC без UI, HTTP и Docker: два раздельных этапа обработки тикета, безопасная генерация через детерминированный или OpenAI-compatible адаптер, SQLite-аудит, demo и детерминированные тесты."
todos:
  - id: setup-contracts
    content: Настроить пакет, зависимости, конфигурацию и контракты данных
    status: pending
  - id: fast-path
    content: Реализовать PII, policy и детерминированную классификацию fast path
    status: pending
  - id: generation-path
    content: Реализовать retrieval, два генератора и проверки ответа
    status: pending
  - id: sqlite-audit
    content: Добавить нормализованный SQLite-аудит и идемпотентность
    status: pending
  - id: demo-tests
    content: Добавить CLI demo, тесты и проверить deterministic/live режимы
    status: pending
  - id: poc-docs
    content: Обновить PoC-раздел README и журнал AI_USAGE
    status: pending
isProject: false
---

# План минимального PoC обработки тикетов

## Границы
- Только локальное Python-приложение: без UI, HTTP API, очереди и Docker.
- Сохранить архитектурную границу через `make_fast_decision()` и `process_generation_job()`: в PoC второй этап вызывается последовательно.
- Rule-based классификатор и маленькая тестовая база знаний явно считаются заменами; реальными остаются валидация контрактов, PII-очистка, TF-IDF retrieval, policy, LLM-интеграция и SQLite-аудит.

## Реализация
1. Настроить пакет и минимальные зависимости в [pyproject.toml](/home/fyodebadylo/projects/system-design-task/pyproject.toml): Pydantic, scikit-learn, OpenAI SDK, dotenv и pytest; создать пакет `src/support_ai` и CLI entry point.
2. В [models.py](/home/fyodebadylo/projects/system-design-task/src/support_ai/models.py) описать валидируемые контракты `Ticket`, прогнозов, fast decision, generation job и итогового helpdesk payload. В небольших сфокусированных модулях реализовать PII-плейсхолдеры, приоритет рискованных правил, keyword-классификатор с confidence и low-confidence abstention.
3. Добавить одобренные версионируемые статьи в [knowledge_articles.json](/home/fyodebadylo/projects/system-design-task/data/knowledge_articles.json) и реальный TF-IDF top-K retrieval. Оркестрацию собрать в [pipeline.py](/home/fyodebadylo/projects/system-design-task/src/support_ai/pipeline.py): риск/неуверенность сразу дают `HUMAN_REVIEW`; безопасный fast path — `AI_PENDING`; retrieval/generation/validation — `AUTO_REPLY_READY` либо fallback оператору.
4. В [generation.py](/home/fyodebadylo/projects/system-design-task/src/support_ai/generation.py) сделать один заменяемый интерфейс генерации: детерминированный режим при неполной LLM-конфигурации и реальный OpenAI-compatible вызов при наличии `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Передавать только очищенный текст и top-K статей, требовать JSON schema, ограничивать токены и проверять `used_article_ids`/PII. Ошибка настроенного реального API должна записываться как `DEPENDENCY_FAILURE` и вести к `HUMAN_REVIEW`, а не маскироваться успешным mock-ответом.
5. В [audit.py](/home/fyodebadylo/projects/system-design-task/src/support_ai/audit.py) создать SQLite-схему, соответствующую минимальной части ER-модели: версии, processing run, append-only decisions, topic predictions, knowledge articles и evidence. Обеспечить идемпотентность по `event_id`; не хранить исходный или очищенный текст. БД размещать по настраиваемому пути `.data/audit.db`, а `.data/` добавить в [.gitignore](/home/fyodebadylo/projects/system-design-task/.gitignore).
6. Обновить [.env.example](/home/fyodebadylo/projects/system-design-task/.env.example) без секретов и добавить demo-команду в [__main__.py](/home/fyodebadylo/projects/system-design-task/src/support_ai/__main__.py). Demo должен показать безопасный happy path, рискованный/low-confidence маршрут оператору и деградацию безопасного тикета при недоступной генерации, печатая итоговые JSON payload и audit-ссылки.

## Проверка и фиксация
- В [tests](/home/fyodebadylo/projects/system-design-task/tests) покрыть валидацию входа, PII до границы LLM, happy path с evidence, запрет автоответа для риска/низкой уверенности, provider failure и идемпотентность; использовать временную SQLite и fake generator, без сетевых вызовов.
- Запустить полный pytest и локальный deterministic demo; затем один ограниченный live smoke через настроенный OpenAI-compatible API, если `.env` заполнен, не выводя ключ или сырой PII.
- Внести только PoC-инструкции запуска и честные границы реализации в [README.md](/home/fyodebadylo/projects/system-design-task/README.md), а вклад AI, выбранные замены и результаты проверок — в [AI_USAGE.md](/home/fyodebadylo/projects/system-design-task/AI_USAGE.md).