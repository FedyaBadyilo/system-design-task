---
description: Summarize the current work block into AI_USAGE.md, focusing on AI contribution and developer ownership.
---

Update `AI_USAGE.md` using the work performed in the current conversation/context.

The purpose is to capture meaningful AI involvement and human ownership of the solution, not to produce a prompt log.

**Language:** all entries added to `AI_USAGE.md` must be written in **Russian** (section headings and bullet content).

Procedure:

1. Summarize the current logical work block.
2. Add one concise entry to `AI_USAGE.md`.
3. Capture:
   - what AI researched, proposed, designed, or implemented;
   - which decisions were made by the developer;
   - what was verified, reviewed, or changed by the developer;
   - what AI suggestions were rejected or corrected, if any.
4. Do not invent decisions, verification steps, or rejected suggestions.
5. Do not copy prompts, conversation transcripts, chain-of-thought, token counts, or low-value interaction history.
6. If there was no meaningful rejected/corrected suggestion, omit that bullet.
7. Preserve existing entries and avoid duplicating information already recorded.
8. Keep each entry short enough to scan quickly later.

Use this format:

```markdown
## <краткое название блока работы>

- **AI contribution:** ...
- **My decisions / verification:** ...
- **Rejected / corrected:** ...   <!-- optional -->
```

Focus on ownership-relevant facts. It is valid for AI to have written most or all implementation code if the developer defined the approach, made architectural decisions, reviewed the result, and validated the behavior.

After editing, briefly confirm which work block was recorded and whether anything was left out because it was already documented.
