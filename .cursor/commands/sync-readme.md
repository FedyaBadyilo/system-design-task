---
description: Synchronize README with the repository's current implementation, run instructions, validation, and real limitations.
---

Update `README.md` so it accurately reflects the current repository.

Use the actual code and task statement as the source of truth.

Procedure:

1. Read the current README and inspect the implementation, entrypoints, configuration, tests, and relevant docs.
2. Preserve a compact structure appropriate to the task instead of forcing a universal template.
3. Ensure the README clearly explains:
   - the problem and implemented solution at a useful level;
   - how to install/run the project;
   - how to execute the main implemented scenario;
   - how to run available tests or validation;
   - important assumptions and limitations when they materially affect the result.
4. Clearly distinguish:
   - implemented components;
   - mocked/stubbed components;
   - design-only components.
5. Remove or correct stale claims that no longer match the code.
6. Do not invent metrics, performance numbers, integrations, reliability guarantees, or capabilities that were not validated.
7. Keep commands copy-pastable and consistent with actual file names and dependencies.
8. Keep the README concise enough to scan quickly. Do not add generic sections that do not help understand or run this project.
9. Do not change implementation code unless a trivial documentation mismatch reveals an obvious typo in a command/path; otherwise report the mismatch.

After editing, summarize the meaningful README changes and any unresolved documentation gaps.
