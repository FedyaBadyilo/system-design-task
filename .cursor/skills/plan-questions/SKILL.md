---
name: plan-questions
description: Create a questions.md planning questionnaire for large, complex, or underspecified implementation tasks before architecture, backlog, or coding. Use when a short task description has many variables, design choices, unclear scope, unclear acceptance criteria, or the user wants controlled planning through editable markdown questions. Do not use for small local changes.
disable-model-invocation: true
---

# Plan Questions

Use this skill to turn a short description of a large or ambiguous task into a focused planning questionnaire.

The goal is not to plan the implementation yet. The goal is to give the user a convenient `questions.md` file where they can make decisions, choose constraints, and clarify what "done" means before architecture, backlog, or code.

## When to Use

Use this skill when the task is:

- broad, cross-cutting, or likely to touch several files or pipeline steps;
- underspecified, with multiple plausible implementation paths;
- dependent on user preferences, domain assumptions, data contracts, artifacts, validation, or non-goals;
- risky enough that coding before clarification could waste time or produce the wrong design.

Do not use this skill for:

- small local edits with obvious scope;
- simple bug fixes where the failing behavior and expected behavior are clear;
- formatting, naming, comments, or mechanical changes;
- tasks where the user already provided sufficient acceptance criteria and constraints.

## Output Location

Create or update:

```text
.cursor/plans/<index>-<name-slug>/questions.md
```

Create `.cursor/plans/<index>-<name-slug>/` if it does not exist. `<name-slug>` — kebab-case from the task description. `<index>` — `01`, `02`, …: next number in `.cursor/plans/` for a new task; reuse the existing folder when continuing. If several name slugs would be reasonable, ask the user to choose before creating files.

If the user provides a specific path, use that path instead.

## Inputs

Use only context that helps ask better questions:

- the user's task description;
- files, folders, docs, logs, screenshots, or planning artifacts explicitly attached or named by the user;
- nearby repository rules or README files when they clearly affect the question set;
- narrow codebase inspection when it prevents obvious or already-answered questions.

Do not perform broad repository exploration by default. Prefer one focused inspection pass over a full architecture review.

Do not create or modify architecture, backlog, implementation code, or unrelated planning artifacts.

## Procedure

1. Decide whether the task is large or underspecified enough for this skill. If not, say that this skill is unnecessary and proceed with the simpler workflow.
2. Identify the plan folder (`<index>-<name-slug>`) and target `questions.md` path.
3. Inspect only the relevant context needed to avoid low-value questions.
4. Create or update `questions.md`.
5. Stop after writing the questions and ask the user to answer them in `questions.md`.

When updating an existing `questions.md`, preserve answered questions unless the user explicitly asks to regenerate them. Add, remove, or reword unanswered questions only when that improves clarity.

## Questions File Structure

Use this structure, adapting sections and question count to the task. Write the `questions.md` file in the same language of the user's task description unless the user asks otherwise.

```md
# Questions - <task title>

## Task Summary

<One short paragraph restating the task as understood. Keep it neutral and avoid adding new requirements.>

## Priority Questions

### 1. <Most important unresolved decision>

**Why it matters:** <one short sentence explaining what implementation decision this controls. Omit this line when the reason is obvious from the question.>

**Answer type:** single choice

- [ ] <option>
- [ ] <option>
- [ ] Other: ...

**Final answer:**

---

### 2. <Next important unresolved decision>

**Why it matters:** <one short sentence, only if useful.>

**Answer type:** single choice

- [ ] <option>
- [ ] <option>
- [ ] Other: ...

**Final answer:**

---

## <Topic Group>

### 3. <Question>

**Why it matters:** <one short sentence, only if useful.>

**Answer type:** multiple choice

- [ ] <option>
- [ ] <option>
- [ ] Other: ...

**Final answer:**
```

## Question Design Rules

Generate the questions dynamically. Do not include every section from the template by default. Use only sections that materially reduce implementation ambiguity.

Good questions are:

- specific to the task and repository context;
- answerable by the user without reading large amounts of code;
- useful for deciding architecture, scope, contracts, artifacts, validation, or non-goals;
- allowed to surface important options, risks, or constraints the user may not have considered in the original task description;
- prioritized so the most blocking decisions come first;
- concise enough that the user can answer the file in one pass.

Prefer:

- `---` separators between questions so the raw `.md` file is easy to scan;
- bold service labels such as `**Answer type:**` and `**Final answer:**`;
- single-choice checkboxes for mutually exclusive decisions;
- multi-choice checkboxes for constraints, affected areas, validation methods, and artifact expectations;
- an `Other:` option whenever the proposed choices may be incomplete.

Avoid:

- purely open questions without predefined options;
- generic questions that do not change implementation decisions;
- asking the user to restate information already present in the request, code, docs, or repository rules;
- asking for file paths unless the task genuinely depends on a specific starting point;
- forcing every question into the same format;
- adding `Why it matters` when it repeats the question or states the obvious;
- generic acceptance criteria or non-goal questions that could apply to any task without modification;
- turning the file into bureaucracy;

## Useful Question Areas

Choose only the areas that matter for the task:

- goal and expected user-visible result;
- scope boundaries and explicit non-goals;
- inputs, outputs, data contracts, and compatibility expectations;
- generated artifacts, logs, reports, or evaluation outputs;
- architecture choices or responsibility boundaries;
- constraints from repository rules, existing patterns, performance, cost, or data availability;
- validation method and acceptance criteria;
- rollout, migration, cleanup, or backwards compatibility when relevant;
- examples of desired and undesired behavior.

## Stop Condition

After creating or updating `questions.md`, stop. Tell the user the file path and ask them to answer the questions there before architecture, backlog, or implementation continues.
