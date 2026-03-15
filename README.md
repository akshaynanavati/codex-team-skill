# Team Skill

Filesystem-based multi-agent team runtime for Codex.

The Team skill lets you:

- create a team workspace (`TEAM_<name>/`)
- recruit members with role files and per-member context
- train one member by refining `ROLE.md` from task and collaboration evidence
- optimize one member's durable context so future runs load cleaner memory
- run one or more member work rounds against a SQLite-backed inbox/task system

The runtime is local-first: all state is stored in your team folder, and message/task records are managed through the bundled CLI.

## What This Skill Provides

- Deterministic workspace scaffolding for teams and members
- Deterministic training snapshots for one member's role, tasks, and cross-member messages
- Deterministic optimize snapshots for one member's role/context/runtime state
- SQLite state store for messages and tasks
- Strict inbox isolation by member identity
- Team-local scheduler wrapper (`TEAM_<name>/run`) that executes runnable members and can batch-train or batch-optimize selected members
- Human-only CEO console wrapper (`TEAM_<name>/ceo`) for oversight

## Repository Layout

```text
team/
├── SKILL.md                  # Agent instructions (create/recruit/train/optimize/execute modes)
├── agents/
│   └── openai.yaml           # UI metadata
└── scripts/
    ├── team_fs.py            # Team/member scaffolding + train/optimize snapshot CLI
    ├── team_cli.py           # SQLite messages/tasks CLI
    ├── team_ceo_cli.py       # Human CEO inbox/task console
    └── run.py                # Central scheduler script used by TEAM_<name>/run wrappers
```

## Requirements

- Python 3.10+
- Codex CLI available as `codex`

## Installation

### Option 1: Install via Skill Installer

Install this skill from:

`https://github.com/akshaynanavati/codex-team-skill`

Run:

```bash
codex exec --skip-git-repo-check 'Use $skill-installer. Install skill from GitHub URL: https://github.com/akshaynanavati/codex-team-skill/tree/main/team'
```

### Option 2: Dev Install via Clone + Symlink

Use this if you want Codex to pick up local changes to the skill without reinstalling.

```bash
git clone 'https://github.com/akshaynanavati/codex-team-skill.git'
cd 'codex-team-skill'
mkdir -p "$CODEX_HOME/skills"
ln -s "$(pwd)"'/team' "$CODEX_HOME/skills/team"
```

If a `team` skill link already exists, remove it first, then create the symlink again.

After either install option, restart Codex so the skill is loaded or reloaded.

## How To Interact With This Skill

Use Codex as the primary interface.

- Preferred: ask Codex to `create`, `recruit`, `train`, `optimize`, or `execute` using the Team skill
- Secondary: run Python CLIs directly only for debugging, verification, or recovery

In normal usage, you should not need to call the Python scripts manually.

## Quick Start

### 1) Create a Team (via Codex)

```bash
codex exec 'Use $team in create mode. Create team demo with mission: Ship reliable weekly customer reporting.'
```

This creates:

- `TEAM_demo/mission.md`
- `TEAM_demo/guidelines.md`
- `TEAM_demo/members/`
- `TEAM_demo/state/`
- `TEAM_demo/ceo`
- `TEAM_demo/run`

You can also do this from an interactive Codex chat by saying:

- "Use `$team` in create mode and create team `demo` with mission `...`"

### 2) Recruit Teammates (via Codex)

```bash
codex exec 'Use $team in recruit mode. Recruit member analyst into team demo with role: Own KPI analysis, investigate anomalies, and escalate blockers quickly.'
codex exec 'Use $team in recruit mode. Recruit member pm into team demo with role: Prioritize work, resolve dependencies, and report progress to CEO.'
```

This creates one folder per member:

- `TEAM_demo/members/analyst/ROLE.md`
- `TEAM_demo/members/analyst/context/`
- `TEAM_demo/members/pm/ROLE.md`
- `TEAM_demo/members/pm/context/`

### 3) Train One Member's Role (via Codex)

Use this when a member's written role has drifted from the work they actually perform:

```bash
codex exec 'Use $team in train mode. Train member analyst in team demo by reviewing the current role, the member tasks, and messages with teammates, then rewrite ROLE.md to reflect the real responsibilities.'
```

Train mode updates `ROLE.md` from runtime evidence. It does not execute tasks or reply to messages.

### 4) Optimize One Member's Context (via Codex)

Use this when a member's `context/` has become noisy, oversized, or stale:

```bash
codex exec 'Use $team in optimize mode. Optimize member analyst in team demo by reviewing the role, current context, and same-member tasks/messages, then rewrite the context into concise high-fidelity files.'
```

Optimize mode does not execute tasks or reply to messages. It only cleans the active member's durable context.

### 5) Execute Work Rounds (via Codex)

Run one member round:

```bash
codex exec 'Use $team in execute mode. Execute one work round for member analyst in team demo.'
```

Run members with the team scheduler:

```bash
./TEAM_demo/run
```

By default, the runner evaluates each member and invokes Codex only for runnable members in execute mode.
Each member run follows `mission.md`, `ROLE.md`, member `context/`, and team `guidelines.md` when present.

Useful options:

```bash
./TEAM_demo/run --dry-run
./TEAM_demo/run --rounds 3
./TEAM_demo/run --rounds -1
./TEAM_demo/run --train
./TEAM_demo/run --optimize --sequential
./TEAM_demo/run --member analyst --sequential
./TEAM_demo/run --allow-member analyst --deny-member pm --rounds 1
./TEAM_demo/run --ignore-ceo-messages
```

`--train` and `--optimize` run exactly one round, ignore `--rounds`, skip the execute-only CEO inbox gate, and run all selected members concurrently unless `--sequential` is set.

Scheduler stop control:

- Create `TEAM_<name>/.stop` to make `TEAM_<name>/run` exit cleanly at the start of the next round.
- `--rounds -1` keeps the scheduler running until that `.stop` file appears, or exits early when no members are eligible to run.

## CEO CLI (Human-Only)

Use the team-scoped wrapper created during team setup:

```bash
./TEAM_demo/ceo
```

You can also launch the underlying script directly:

```bash
python3 team/scripts/team_ceo_cli.py --base . --team demo
```

Important behavior:

- `team_ceo_cli.py` is intentionally blocked in agent runtime environments.
- It requires an interactive TTY (`stdin` and `stdout` must be interactive).
- The CEO console reads and writes the same SQLite state used by member runs (`TEAM_<name>/state/team_state.sqlite3`).

### CEO Menu Actions

When the CEO console opens, it provides:

1. Send a message to a member
2. View CEO inbox
3. Add scheduler `.stop` file, or remove it when already present
4. View messages table
5. View tasks table

Option `3` toggles `TEAM_<name>/.stop`, which is the same stop file checked by `TEAM_<name>/run`.

Navigation controls:

- Use `Up` / `Down` arrows to move through the main menu.
- Press `Enter` to open the selected view.
- Press `b` to go back in screen history.
- Press `f` to go forward in screen history.
- Press `q` to close the current screen (or quit from the main menu).
- In task/message tables, use `Up` / `Down` to move row selection and `Enter` to open the selected item.
- Task table hotkeys: `/` text filter, `o` owner filter, `s` scope cycle, `l` limit, `c` clear filters.
- Message table hotkeys: `/` text filter, `o` sender filter, `d` receiver filter, `s` scope cycle, `l` limit, `c` clear filters, `a` archive hovered row, `u` unarchive hovered row.
- In task/message detail views, use arrow keys to move a readonly cursor over text.
- Press `Enter` on a hovered ID (full UUID or unique suffix) to open the linked task/message.
- Prefixed references in text are also supported, including `[msg:<uuid>]` / `msg:<uuid>` and `[task:<uuid>]` / `task:<uuid>`.
- Message detail includes a `tasks_created_from_message` section; press `Enter` on a hovered `task_id` there to jump to task detail.
- In CEO inbox message detail views, press `r` to open an inline reply draft panel below the open message.
- In reply and compose draft panels, use arrow keys to move the cursor, `F2` to send, and `F1` to discard (`Ctrl-S`/`Ctrl-Q` are also supported when the terminal allows them).

### Inbox and Status Behavior

- New messages start as `unread`.
- Opening a message marks it `read`.
- After opening a message, the UI prompts to archive it.
- Archiving sets status to `archived` and removes it from normal inbox views.
- Unarchive from the message table with `u` on an archived hovered row; status returns to `read`.

### CEO Escalations and Scheduler Gate

Escalation flow:

1. A member escalates by sending a message to receiver `ceo` (usually during execute mode when blocked/ambiguous).
2. Before each scheduler round, unread CEO messages are checked.
3. If unread CEO messages exist, scheduler pauses and prompts for human intervention by default.
4. CEO uses `./TEAM_<name>/ceo` (option `3`) to review and respond.
5. Once CEO unread count is cleared, scheduler can continue.

Notes:

- The scheduler gate checks `unread` only. Reading a CEO message clears the unread state; archiving is optional.
- In non-interactive runs, the gate cannot prompt and the scheduler exits with failure until the CEO inbox is handled.
- To bypass this gate for a run, pass `--ignore-ceo-messages` to `TEAM_<name>/run`.

## Complete Example: Build and Operate a 4-Member Team

This example creates one team with four members (max shown here), then runs and manages work using `TEAM_<name>/run` and the human CEO CLI.

### 1) Create the Team

```bash
codex exec 'Use $team in create mode. Create team launch_ops with mission: Plan and execute a reliable product launch with clear ownership, fast escalation, and weekly reporting.'
```

What this does:

- Creates `TEAM_launch_ops/` with mission/guidelines files, members/state directories, `run`, and `ceo` wrappers.
- Initializes the runtime SQLite database used by tasks/messages.

### 2) Recruit Four Members (via Codex)

```bash
codex exec 'Use $team in recruit mode. Recruit member pm into team launch_ops with role: Own launch plan, prioritize work, and coordinate dependencies across all members.'
codex exec 'Use $team in recruit mode. Recruit member analyst into team launch_ops with role: Track launch metrics, investigate anomalies, and escalate blockers to CEO quickly.'
codex exec 'Use $team in recruit mode. Recruit member engineer into team launch_ops with role: Deliver technical launch work, report risks early, and keep task state current.'
codex exec 'Use $team in recruit mode. Recruit member qa into team launch_ops with role: Validate release quality, triage defects, and escalate release-stopping issues immediately.'
```

What this does:

- Creates `ROLE.md` and `context/` for each member under `TEAM_launch_ops/members/`.

### 3) Seed Initial Work from the Human CEO Console

Open the CEO CLI:

```bash
./TEAM_launch_ops/ceo
```

In the menu:

1. Choose `1) Send a message to a member` and send kickoff messages to `pm`, `analyst`, `engineer`, and `qa`.
2. Use `2) View CEO inbox` to monitor escalations coming back to CEO.
3. Open an inbox message and press `r` to reply inline when needed.

### 4) Preview Which Members Will Run

```bash
./TEAM_launch_ops/run --dry-run
```

What this does:

- Evaluates each member's run criteria.
- Prints runnable members and planned `codex exec` calls without running them.

### 5) Execute Scheduler Rounds

Run one full round (concurrent by default):

```bash
./TEAM_launch_ops/run --rounds 1
```

Run two rounds sequentially (easier to observe in order):

```bash
./TEAM_launch_ops/run --rounds 2 --sequential
```

Batch-train every member once:

```bash
./TEAM_launch_ops/run --train
```

Batch-optimize every member once in sequence:

```bash
./TEAM_launch_ops/run --optimize --sequential
```

### 6) Handle Escalations During Runs

If `./TEAM_launch_ops/run` pauses because CEO has unread messages:

1. Open the CEO CLI in another terminal: `./TEAM_launch_ops/ceo`
2. Choose `2) View CEO inbox` and open unread messages.
3. Press `r` from the message detail view when a reply is needed.
4. Return to the paused runner and continue.

If you intentionally want rounds to continue without waiting on CEO inbox, run with:

```bash
./TEAM_launch_ops/run --ignore-ceo-messages
```

### 7) Ongoing Management Commands

Run only specific members:

```bash
./TEAM_launch_ops/run --member pm --member engineer --rounds 1 --sequential
```

Run with explicit model/effort:

```bash
./TEAM_launch_ops/run --model gpt-5.3-codex --reasoning-effort medium --rounds 1
```

Train or optimize only a subset of members:

```bash
./TEAM_launch_ops/run --train --member pm --member engineer
./TEAM_launch_ops/run --optimize --member analyst --sequential
```

Use CEO CLI continuously for oversight:

```bash
./TEAM_launch_ops/ceo
```

## Appendix: Under-The-Hood Python Commands (Debugging)

Codex runs these flows for you. Use these commands when you need to inspect behavior or debug state directly.

Initialize/verify DB:

```bash
python3 scripts/team_cli.py --base <dir> --team <team> init
```

Create team and recruit members:

```bash
python3 scripts/team_fs.py --base <dir> create --name <team-name> --mission '<mission>' [--guidelines '<team-rules>']
python3 scripts/team_fs.py --base <dir> recruit --team <team-name-or-path> --name <member-name> --role '<role>'
```

Messages:

```bash
python3 scripts/team_cli.py --base <dir> --team <team> message send --sender <sender> --receiver <receiver> --body '<text>' [--subject '<subject>'] [--task-id <uuid>]
python3 scripts/team_cli.py --base <dir> --team <team> message list --member <member> [--status inbox|unread|read|archived|all]
python3 scripts/team_cli.py --base <dir> --team <team> message read --member <member> --message-id <uuid>
python3 scripts/team_cli.py --base <dir> --team <team> message archive --member <member> --message-id <uuid>
python3 scripts/team_cli.py --base <dir> --team <team> message list-archived --member <member>
```

Tasks:

```bash
python3 scripts/team_cli.py --base <dir> --team <team> task create --owner <member> --body '<task>' [--priority <int>] [--created-by <actor>]
python3 scripts/team_cli.py --base <dir> --team <team> task list [--owner <member>] [--state open|all|todo|in_progress|blocked|done|cancelled]
python3 scripts/team_cli.py --base <dir> --team <team> task show --task-id <uuid>
python3 scripts/team_cli.py --base <dir> --team <team> task update-state --task-id <uuid> --state <state> [--reason '<reason>']
```

For `team_cli.py`, place `--json` before `init`, `message`, or `task` when you need machine-readable output, for example:

```bash
python3 scripts/team_cli.py --base <dir> --team <team> --json task list [--owner <member>] [--state open|all|todo|in_progress|blocked|done|cancelled]
```

`team_fs.py optimize/train` support `--json` on the subcommand itself as shown below. `team_fs.py create/recruit` do not support `--json`.

Optimize snapshot:

```bash
python3 scripts/team_fs.py --base <dir> optimize --team <team-name-or-path> --name <member-name> [--task-limit <n>] [--message-limit <n>] [--json]
```

## Execution Model

The skill defines four exclusive operating modes per run:

1. `create`
2. `recruit`
3. `optimize`
4. `execute`

When a member is optimized:

- `ROLE.md` is treated as the source of truth for what durable context should exist
- same-member tasks/messages can be inspected to judge whether context is still relevant
- large or mixed-purpose context files should be split, condensed, or deleted
- runtime task/message state should not be mutated unless explicitly requested

When a member executes work:

- inbox messages are processed first
- actionable items become task records
- exactly one highest-priority task is attempted per run
- unresolved ambiguity is escalated to `ceo` and task state is set to `blocked`

## Safety and Access Rules

- Member runs should only access that member's inbox (`--member <active-member>`)
- Member runs should not read other members' inboxes
- `team_ceo_cli.py` is for a human CEO terminal session only
- Never fabricate IDs or database state; use runtime CLI commands

## Notes for Open-Sourcing

- Keep `SKILL.md` as the source of truth for agent behavior and constraints
- Keep CLI examples in this README aligned with `scripts/* --help` output
- Consider adding automated smoke tests for:
  - create/recruit scaffolding
  - train snapshot flow
  - optimize snapshot flow
  - `team_cli.py init/message/task` flows
  - runner `--dry-run` behavior
