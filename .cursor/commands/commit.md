---
description: Review the working tree and commit current changes in meaningful logical groups with clear commit messages.
---

Commit the current repository changes by logical blocks.

Procedure:

1. Read the repository rules relevant to Git and code changes.
2. Run `git status` and inspect the current diff.
3. Exclude secrets, local environment files, caches, generated junk, and unrelated changes.
4. Group the remaining changes by completed logical purpose.
5. If there are multiple independent groups, commit them separately.
6. Before each commit, run the smallest relevant validation when practical.
7. Stage only the files or hunks belonging to that group.
8. Use concise commit messages in this style when appropriate:

   `feat: ...`
   `fix: ...`
   `test: ...`
   `docs: ...`
   `refactor: ...`
   `chore: ...`

9. Do not create meaningless micro-commits and do not use vague messages such as `update`, `fix2`, `changes`, or `final`.
10. Do not amend, rebase, reset, force-push, or rewrite existing history unless explicitly requested.
11. Finish by showing the commits created and the remaining `git status`.

If the working tree contains changes that are ambiguous, risky to split, or appear unrelated to the current task, leave them uncommitted and report them instead of guessing.
