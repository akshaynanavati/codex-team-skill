---
name: team
description: "Create and operate filesystem-based teams in exactly one mode per run: (1) create a team workspace, (2) recruit a member, (3) update a team-local runner from the latest template while preserving local customizations, or (4) execute one work round for a specific member. Use when asked to initialize `TEAM_<name>/` with `members/`, `state/`, and `mission.md`, add `members/<name>/ROLE.md` plus `context/`, refresh `TEAM_<name>/run.py` from `skills/team/scripts/run.py`, or run a mission-aligned member cycle with strict message isolation and SQLite-backed message/task state through the bundled team CLI."
---

# Team

Run exactly one mode per invocation: `create`, `recruit`, `update-run-script`, or `execute`.

## Mode Router (Required First Step)

Choose mode before any filesystem write.

- `create`: initialize one new team workspace.
- `recruit`: add one member to an existing team.
- `update-run-script`: merge latest runner template into one team-local runner.
- `execute`: run one work round for one member.

If intent is ambiguous, ask one clarifying question and stop.

## Global Rules

### Naming and Paths

- Use the invocation directory as default `--base`.
- Team path format: `TEAM_<team-name>/`.
- Member path format: `TEAM_<team-name>/members/<member-name>/`.
- Reject names containing `/` or `\`.
- Names should match `^[A-Za-z0-9._-]+$`.

### Script Setup

Set script paths first:

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export TEAM_FS_CLI="$CODEX_HOME/skills/team/scripts/team_fs.py"
export TEAM_RUNTIME_CLI="$CODEX_HOME/skills/team/scripts/team_cli.py"
export TEAM_CEO_CLI="$CODEX_HOME/skills/team/scripts/team_ceo_cli.py"
export TEAM_RUNNER_TEMPLATE="$CODEX_HOME/skills/team/scripts/run.py"
```

### Script-First Boundary

Use scripts for deterministic writes and state transitions.

- Team scaffolding and member scaffolding: `team_fs.py`.
- Message/task state creation and updates: `team_cli.py`.
- Team scheduling: team-local `TEAM_<name>/run.py` copied from template.
- Human CEO terminal only: `team_ceo_cli.py`.

Do not hand-edit SQLite state when an equivalent CLI command exists.

### Runtime State (SQLite)

- Persist runtime state in `TEAM_<team-name>/state/team_state.sqlite3`.
- Core tables:
  - `messages`: `message_id`, `sender`, `receiver`, `subject`, `body`, `created_at`, `status` (`unread|read|archived`), `read_at`, `archived_at`, `task_id` (optional).
  - `tasks`: `task_id`, `owner`, `state` (`todo|in_progress|blocked|done|cancelled`), `body`, `priority`, `created_by`, `created_at`, `updated_at`, `blocked_reason`.
- Never fabricate UUIDs; use CLI-generated IDs only.
- Assume concurrent workers; runtime CLI handles WAL mode, busy timeout, and retrying write transactions.

### Access Constraints

- Member runs may list/read/archive only that member's inbox using `--member <active-member>`.
- Never read another member's inbox in a member run.
- Never read CEO inbox in normal member runs.
- Sending to CEO is allowed (`--receiver ceo`) for escalations.
- Never run `team_ceo_cli.py` from an agent invocation.

### CEO Console (Human Only)

Human terminal usage:

```bash
python3 "$TEAM_CEO_CLI" --base "<directory>" --team "<team-name-or-path>"
./TEAM_<name>/ceo [extra flags]
```

The CEO console is the human interface for browsing tasks/messages (including member and CEO inboxes), unarchiving member messages, and sending replies/new CEO messages.

## Mode: Create

Use only when asked to create a team.

Run:

```bash
python3 "$TEAM_FS_CLI" --base "<directory>" create --name "<team-name>" --mission "<mission text>"
```

Resulting structure:

- `TEAM_<name>/`
- `TEAM_<name>/members/`
- `TEAM_<name>/state/`
- `TEAM_<name>/mission.md`
- `TEAM_<name>/ceo`
- `TEAM_<name>/run.py`

Rules:

- Write `mission.md` from provided mission text.
- If mission is missing, write a short placeholder and ask for mission details.
- Initialize runtime DB schema:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<name-or-path>" init
```

- `create` writes executable `TEAM_<name>/ceo` wrapper bound to that team.
- `create` copies `TEAM_<name>/run.py` from `$TEAM_RUNNER_TEMPLATE`.
- Do not recruit members in this mode.

## Mode: Recruit

Use only when asked to recruit one member.

Precondition: team directory exists.

Run:

```bash
python3 "$TEAM_FS_CLI" --base "<directory>" recruit --team "<team-name-or-path>" --name "<member-name>" --role "<role text>" [--run-check "<criteria text>"]
```

Resulting member structure:

- `members/<member-name>/`
- `members/<member-name>/ROLE.md`
- `members/<member-name>/context/`

Rules:

- Write `ROLE.md` exactly from provided role text.
- If role text is missing, write a short placeholder and ask for role details.
- If custom run criteria is provided, pass `--run-check` to inject a member-specific stub into team-local `run.py`.
- Do not create or edit other members in this mode.

## Mode: Update Run Script

Use only when asked to update one team-local runner from the latest template.

Preconditions:

- Team directory exists.
- `TEAM_<name>/run.py` exists.
- `$TEAM_RUNNER_TEMPLATE` exists and points to `skills/team/scripts/run.py`.

Required sequence:

1. Resolve paths and create a backup of local runner.
- Local: `TEAM_<name>/run.py`
- Template: `$TEAM_RUNNER_TEMPLATE`

2. Diff template vs local and classify hunks.
- Additions-only in template.
- Additions+deletions in template with no overlap against local custom behavior.
- Conflicting edits where template changes overlap local custom behavior.

3. Apply by class.
- Additions-only: apply additions, keep local lines.
- Non-conflicting additions+deletions: apply both so local picks up latest template behavior.
- Conflicts: manual merge. First align to latest template structure, then re-apply local behavior from backup.

4. Validate and finalize.
- Keep executable bit: `chmod +x TEAM_<name>/run.py`.
- Preserve `# TEAM_RUN_CUSTOM_CHECKS` and existing member registrations unless intentionally removed.
- Validate syntax: `python3 -m py_compile "TEAM_<name>/run.py"`.
- Validate wiring: `python3 "./TEAM_<name>/run.py" --dry-run`.

Hard constraints:

- Edit only `TEAM_<name>/run.py` in this mode.
- Never silently drop local custom logic.
- If merge choice is uncertain, preserve local behavior and call out the decision.
- Execute this mode only.

## Team Runner (`TEAM_<name>/run.py`)

Use the runner for scheduler-style execution:

```bash
python3 "./TEAM_<name>/run.py"
python3 "./TEAM_<name>/run.py" --rounds <n>
python3 "./TEAM_<name>/run.py" --model "gpt-5.3-codex" --reasoning-effort medium
python3 "./TEAM_<name>/run.py" --sequential
```

Semantics:

- For every non-dry-run member execution, append current UTC timestamp to `members/<member>/.run`.
- `--rounds` default is `1`.
- Each round evaluates run criteria first, then runs runnable members.
- Default is concurrent runs with per-round barrier before next round.
- `--sequential` runs members one at a time.
- Before each round, runner checks unread CEO inbox messages (`receiver = ceo`, `status = unread`). If any exist, pause for human handling and re-check after confirmation.
- Member runs use project root (parent of `TEAM_<name>/`) as Codex working directory.
- Defaults: `--model gpt-5.3-codex`, `--reasoning-effort medium`.

Default per-member run criteria:

- At least one unread message for that member, or
- At least one actionable task (`todo` or `in_progress`) for that member.

Customize team criteria by editing `TEAM_<name>/run.py`.
For member-specific criteria at recruit time, use `--run-check` then refine the generated stub.

## Mode: Execute

Use only when asked to execute one work round for one member.

Preconditions:

- `TEAM_<name>/mission.md` exists.
- `members/<member>/ROLE.md` exists.
- `members/<member>/context/` exists (create if missing).
- Runtime CLI is available.

Execute this sequence each run:

0. Setup
- Append current UTC timestamp to `members/<member>/.run` (create file if needed).
- Load and follow `mission.md`.
- Load and follow `ROLE.md` exactly as written.
- Load only relevant markdown files from `context/`.

1. Phase 1: Task Completion
- List open tasks for active member.
- Prioritize existing `in_progress` tasks before starting new tasks.
- If none are `in_progress`, select highest-priority next task(s).
- If tasks are tightly related, complete them together in one coherent effort.
- Do not execute multiple unrelated tasks in one run.
- Minimize leftover `in_progress` tasks.
- If selected task is ambiguous/conflicting/not completable, escalate to CEO and set it `blocked` with reason.

2. Phase 2: Message Processing
- List unarchived inbox messages for active member; process unread first.
- Read by `message_id` and action all inbox work for this run.
- Complete quick actions immediately.
- For non-quick actions, create concrete tasks and include source `message_id` for traceability.
- Archive only when fully actioned now, or when created tasks fully cover follow-up.
- If response is required, send it now.
- If response must happen later, capture that obligation explicitly in task state.

3. Phase 3: Prioritization
- Review all member tasks (`todo`, `in_progress`, `blocked`).
- Cancel stale tasks with reason.
- Merge duplicate tasks and preserve traceability in remaining task text.
- Split large tasks into smaller, concrete, single-purpose tasks.
- Reassign priority across full task set each run.

4. Close-out
- Update/clean member context files.
- Write short summary to `state/<member>-last-run.md` with timestamp, handled task IDs, and blockers/escalations.

Hard constraints:

- Run phases in order: Task Completion -> Message Processing -> Prioritization.
- Never archive actionable work unless completed now or represented by task records.
- Prefer many small single-purpose tasks over one large task.
- Prioritize finishing `in_progress` before starting unrelated new work.
- Keep actions mission-aligned.
- If mission and role conflict, escalate to CEO and mark selected task `blocked`.
- If runtime CLI is unavailable, report blocker and never fabricate state.
- Never read messages not addressed to active member.
- Never modify task state for another member.

## Runtime CLI Commands

Initialization:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" init
```

Messages:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message send --sender "<sender>" --receiver "<receiver-or-ceo>" --body "<message>" [--subject "<subject>"] [--task-id "<task-uuid>"]
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message list --member "<member>" [--status inbox|unread|read|archived|all] [--sender "<sender>"] [--limit <n>]
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message read --member "<member>" --message-id "<message-uuid>"
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message archive --member "<member>" --message-id "<message-uuid>"
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message list-archived --member "<member>" [--limit <n>]
```

Tasks:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task create --owner "<member>" --body "<task body>" [--state todo|in_progress|blocked|done|cancelled] [--priority <int>] [--created-by "<actor>"]
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task list [--owner "<member>"] [--state open|all|todo|in_progress|blocked|done|cancelled] [--limit <n>]
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task show --task-id "<task-uuid>"
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task update-state --task-id "<task-uuid>" --state "<todo|in_progress|blocked|done|cancelled>" [--reason "<note>"]
```

- Add top-level `--json` for machine-readable output.
- Require `--reason` when setting task state to `blocked`.

## IDs and Traceability

- Preserve `message_id` and `task_id` exactly as generated.
- Include relevant IDs in replies, task updates, and escalations.
- Include `task_id` in escalation messages when escalation is task-driven.

## Minimal File Templates

`mission.md`:

```markdown
# Mission
<mission text>
```

`ROLE.md`:

```markdown
# Role
<member role and operating constraints>
```
