---
name: team
description: "Create and operate filesystem-based teams in exactly one mode per run: (1) create a team workspace, (2) recruit a member, or (3) execute one work round for a specific member. Use when asked to initialize `TEAM_<name>/` with `members/`, `state/`, and `mission.md`, add `members/<name>/ROLE.md` plus `context/`, or run a mission-aligned member cycle with strict message isolation and SQLite-backed message/task state through the bundled team CLI."
---

# Team

Run exactly one mode per invocation: `create`, `recruit`, or `execute`.

## Mode Router (Required First Step)

Determine mode before any filesystem write.

- `create`: initialize a new team workspace.
- `recruit`: add one member to an existing team.
- `execute`: run one work round for one member.

If user intent is ambiguous, ask one clarifying question and stop.

## Global Rules

### Naming and Paths

- Treat the invocation directory as the default base path.
- Team path format: `TEAM_<team-name>/`.
- Member path format: `TEAM_<team-name>/members/<member-name>/`.
- Reject names containing `/` or `\`.

### Bundled Scripts

Set script paths first:

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export TEAM_FS_CLI="$CODEX_HOME/skills/team/scripts/team_fs.py"
export TEAM_RUNTIME_CLI="$CODEX_HOME/skills/team/scripts/team_cli.py"
export TEAM_CEO_CLI="$CODEX_HOME/skills/team/scripts/team_ceo_cli.py"
export TEAM_RUNNER_TEMPLATE="$CODEX_HOME/skills/team/scripts/run.py"
```

Use setup script for `create` and `recruit`:

```bash
python3 "$TEAM_FS_CLI" --base "<directory>" create --name "<team-name>" --mission "<mission text>"
python3 "$TEAM_FS_CLI" --base "<directory>" recruit --team "<team-name-or-path>" --name "<member-name>" --role "<role text>" [--run-check "<criteria text>"]
```

Use runtime script to initialize message/task state:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" init
```

`$TEAM_CEO_CLI` is for a human CEO terminal session only. Never execute it from an agent run.

### Runtime State (SQLite)

- Persist all runtime state in `TEAM_<team-name>/state/team_state.sqlite3`.
- Expect exactly two core tables:
  - `messages`: `message_id` (UUID), `sender`, `receiver`, `subject`, `body`, `created_at`, `status` (`unread|read|archived`), `read_at`, `archived_at`, `task_id` (optional UUID reference).
  - `tasks`: `task_id` (UUID), `owner`, `state` (`todo|in_progress|blocked|done|cancelled`), `body`, `priority`, `created_by`, `created_at`, `updated_at`, `blocked_reason`.
- Rely on CLI-generated UUIDs only. Never fabricate IDs.
- Assume concurrent workers. Runtime CLI uses WAL journal mode, busy timeout, and short retrying `BEGIN IMMEDIATE` write transactions.

### Access Constraints

- Allow a member to list/read/archive only their own inbox messages using `--member <active-member>`.
- Disallow reading any other member's inbox.
- Disallow reading CEO inbox in normal member runs; allow sending to CEO (`--receiver ceo`) for escalation.
- Never run `team_ceo_cli.py` from an agent invocation.

### CEO Console (Human Only)

Use only in a direct human terminal:

```bash
python3 "$TEAM_CEO_CLI" --base "<directory>" --team "<team-name-or-path>"
```

Preferred for a specific team after bootstrap:

```bash
./TEAM_<name>/ceo [extra flags]
```

Capabilities:

- View tasks filtered by member.
- View all tasks in a one-row-per-task table with numbered selection and task detail drill-down.
- View all messages in a one-row-per-message table with numbered selection and message detail drill-down.
- View messages for any member inbox.
- View CEO inbox quickly.
- Prompt whether to archive a message immediately after opening it in the CEO console.
- Unarchive archived member messages on behalf of members from the CEO console.
- Send CEO replies to message senders.
- Send new CEO messages directly to a member inbox.
- Select displayed tasks/messages by row number (instead of UUID) to open details.

## Mode: Create

Use only when asked to create a team.

Create this structure:

- `TEAM_<name>/`
- `TEAM_<name>/members/`
- `TEAM_<name>/state/`
- `TEAM_<name>/mission.md`
- `TEAM_<name>/ceo` (team-scoped CEO CLI wrapper; forwards extra flags)
- `TEAM_<name>/run.py` (team-scoped member scheduler; copied from `$TEAM_RUNNER_TEMPLATE`)

Write `mission.md` with user-provided mission text. If missing, write a short placeholder and ask for mission details.

Initialize runtime DB schema:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<name-or-path>" init
```

- Create flow writes executable wrapper `TEAM_<name>/ceo` that binds `--team` to that team and forwards all additional flags to `$TEAM_CEO_CLI`.
- Create flow copies `TEAM_<name>/run.py` from `$TEAM_RUNNER_TEMPLATE` for team-specific scheduling customization.

Do not recruit members in this mode.

## Mode: Recruit

Use only when asked to recruit one member.

Preconditions:

- Team directory exists.

Create this member structure:

- `members/<member-name>/`
- `members/<member-name>/ROLE.md`
- `members/<member-name>/context/`

Write `ROLE.md` with exact user-provided role text. If missing, write a short placeholder and ask for role details.
If custom run criteria is provided at recruit time, pass `--run-check "<criteria>"` so the team-local `run.py` is updated with a member-specific check stub.

Do not create or edit other members in this mode.

## Team Runner (`TEAM_<name>/run.py`)

Use this script to run all members that currently need a work round:

```bash
python3 "./TEAM_<name>/run.py"
python3 "./TEAM_<name>/run.py" --rounds <n>
python3 "./TEAM_<name>/run.py" --model "gpt-5.3-codex" --reasoning-effort medium
python3 "./TEAM_<name>/run.py" --sequential
```

For every non-dry-run member execution, append the current UTC timestamp as a new line in `members/<member>/.run`.
`--rounds` defaults to `1`. In each round, evaluate run criteria first, then run runnable members. By default, runs launch concurrently (at most one active invocation per member), then wait for all runnable members to finish before starting the next round. With `--sequential`, run members one at a time in scheduler order.
Before evaluating members in each round, the runner checks unread CEO inbox messages (`receiver = ceo`, `status = unread`). If any exist, pause and prompt the human to address CEO inbox messages; re-check only after human confirmation.
Use project root (the parent directory of `TEAM_<name>/`) as the Codex working directory for member runs.
`--model` defaults to `gpt-5.3-codex` and `--reasoning-effort` defaults to `medium`.

Default run criteria per member:

- At least one unread message in `messages` (`status = unread`) for that member.
- Or at least one actionable task in `tasks` (`state IN (todo, in_progress)`) for that member.

Customize per team by editing `TEAM_<name>/run.py` directly.
For member-specific criteria introduced during recruit, use `--run-check` to inject a check stub for that member, then refine the generated function.

## Mode: Execute

Use only when asked to execute one work round for one member.

Preconditions:

- `TEAM_<name>/mission.md` exists.
- `members/<member>/ROLE.md` exists.
- `members/<member>/context/` exists (create if missing).
- Runtime CLI is available.

Execute this sequence each run:

0. Setup:
- Append current UTC timestamp to `members/<member>/.run` (create file if missing).
- Load and follow `mission.md`.
- Load and follow `ROLE.md` exactly as written.
- Load only relevant markdown files from `context/`.

1. Phase 1 - Task Completion:
- List open tasks for the active member.
- Prioritize completing existing `in_progress` tasks before starting any new task.
- If there are no `in_progress` tasks, select the next highest-priority task(s).
- If multiple tasks are tightly related and can be completed together in one coherent effort, execute them in the same run.
- Do not pick up multiple unrelated tasks in the same run.
- Minimize the number of tasks left in `in_progress`; prefer pushing started work to `done` or `blocked`.
- If a selected task is ambiguous, conflicting, or not currently completable, escalate to `ceo` and set that task to `blocked` with a reason.

2. Phase 2 - Message Processing:
- List unarchived inbox messages for the active member and process unread first.
- Read each message by `message_id`, then process every message until inbox work for this run is actioned.
- If an action item is quick, do it immediately in this phase.
- If an action item is not quick, create one or more concrete tasks and include the source `message_id` for traceability.
- Archive a message only when it is fully actioned now, or when created tasks fully cover required follow-up.
- If a message requires a response, send the response now; if response must occur later, record that requirement explicitly in the relevant task.
- Do not leave messages awaiting expected teammate response without either replying or creating explicit response-tracking work.

3. Phase 3 - Prioritization:
- Review all tasks for the active member (`todo`, `in_progress`, and `blocked`).
- Cancel tasks that are no longer relevant, with a reason.
- Merge duplicate tasks and preserve traceability in the surviving task text.
- Split large tasks into smaller, concrete, single-purpose tasks.
- Re-assign priority across the current full task set every run, even if tasks already have priorities.

4. Close-out:
- Update or clean up member context files.
- Write a short run summary to `state/<member>-last-run.md` with timestamp, handled `task_id`/`task_id`s, and blockers/escalations.

Hard constraints:

- Run phases in order: Task Completion, Message Processing, then Prioritization.
- Never archive a message with actionable work unless that work is fully completed now or represented by corresponding task records.
- Prefer many small tasks over one large task; keep each task single-purpose and self-contained.
- Prioritize finishing `in_progress` work before starting new work.
- Do not execute multiple unrelated tasks in one run.
- Ensure teammates receive required responses; if not immediate, capture the response obligation in task state.
- Keep actions mission-aligned.
- If mission and role conflict, escalate to CEO and mark chosen task blocked.
- If runtime CLI is missing or unavailable, report blocker; never fabricate message/task state.
- Never read messages not addressed to active member.
- Never modify task state for another member.

## Runtime CLI Commands

Command patterns:

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

- Preserve message IDs and task IDs exactly as generated by runtime CLI.
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
