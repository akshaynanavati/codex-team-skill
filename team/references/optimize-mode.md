# Optimize Mode

Use this file only for `optimize` mode.

## Load Only These References

- Load [optimize-commands.md](optimize-commands.md) before editing files or inspecting runtime state.

## Goal

Keep `members/<member>/context/` as durable, high-fidelity memory for future runs.

- Preserve information that should help the member on nearly every run.
- Remove information that is stale, duplicated, or already represented elsewhere.
- Split mixed or oversized files into smaller topical notes.

## Preconditions

- Ensure `TEAM_<name>/mission.md` exists.
- Ensure `members/<member>/ROLE.md` exists.
- Ensure `members/<member>/context/` exists; if missing, report it and continue with an empty context view.
- Run the optimize inspection command from [optimize-commands.md](optimize-commands.md) before choosing files to edit.

## Step 0: Load Only What You Need

- Read `ROLE.md` first and treat it as the contract for what durable context should exist.
- Read `mission.md` only if the member context should be reconciled against current team direction.
- Use the optimize snapshot to choose which context files to open.
- Inspect only the active member's tasks and messages when context staleness is unclear.
- Never read another member's inbox and never read CEO inbox in this mode.

## Step 1: Understand The Member Contract

- Extract recurring responsibilities, constraints, and decision rights from `ROLE.md`.
- Separate stable role expectations from one-off assignments.
- Treat stable role expectations as the standard for what belongs in durable context.

## Step 2: Audit Current Context

- Identify large files that exceed roughly 200 lines or 8 KiB.
- Identify files that mix multiple unrelated topics or workstreams.
- Identify chronological logs, resolved debates, and stale checklists that do not help future runs.
- Promote recurring knowledge into its own topical file when it does not already exist.

## Step 3: Use Runtime State To Judge Freshness

- Review same-member task lists to see which workstreams are still active, blocked, or done.
- Review same-member message lists to confirm whether a context note still matters or was superseded.
- Read specific tasks or messages by ID only when the snapshot suggests they are relevant.
- Prefer deleting stale context when the authoritative source is a completed task, archived message, or obsolete plan.

## Step 4: Refactor The Context

- Edit only files inside `members/<member>/context/` unless the user explicitly asks for broader changes.
- Prefer multiple small topical files over one large mixed-purpose file.
- Split oversized files by topic, project, customer, system, or recurring workflow.
- Give each file a narrow purpose and a clear filename.
- Rewrite verbose prose into concise bullets when precision is preserved.
- Keep source IDs only when future runs genuinely need traceability back to a task or message.
- Preserve active constraints, recurring decisions, reference links, and durable operating knowledge.
- Remove append-only run logs; those belong in `state/<member>-last-run.md`, not in `context/`.

## Step 5: Validate The Result

- Re-read the changed files and check that each one would be worth loading in a future run.
- Ensure important durable knowledge from the original files still exists somewhere.
- Ensure no file remains a mixed-purpose dumping ground unless there is a strong reason.
- Re-run the optimize inspection command if needed to confirm large-file cleanup.

## Hard Constraints

- Do not execute tasks in this mode.
- Do not reply to or archive messages in this mode.
- Do not create, update, or cancel task records in this mode unless the user explicitly asks.
- Do not edit another member's files while optimizing one member.
- Prefer concise durable memory over exhaustive historical notes.
