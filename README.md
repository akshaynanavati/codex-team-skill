# Team Skill

Filesystem-based multi-agent team runtime for Codex.

The Team skill lets you:

- create a team workspace (`TEAM_<name>/`)
- recruit members with role files and per-member context
- run one or more member work rounds against a SQLite-backed inbox/task system

The runtime is local-first: all state is stored in your team folder, and message/task records are managed through the bundled CLI.

## What This Skill Provides

- Deterministic workspace scaffolding for teams and members
- SQLite state store for messages and tasks
- Strict inbox isolation by member identity
- Team scheduler (`run.py`) that triggers member runs from inbox/tasks
- Human-only CEO console wrapper (`TEAM_<name>/ceo`) for oversight

## Repository Layout

```text
team/
├── SKILL.md                  # Agent instructions (create/recruit/execute modes)
├── agents/
│   └── openai.yaml           # UI metadata
└── scripts/
    ├── team_fs.py            # Team/member filesystem scaffolding CLI
    ├── team_cli.py           # SQLite messages/tasks CLI
    ├── team_ceo_cli.py       # Human CEO inbox/task console
    └── run.py                # Team runner template copied into TEAM_<name>/
```

## Requirements

- Python 3.10+
- Codex CLI available as `codex`

## Installation

Install this skill from:

`https://github.com/akshaynanavati/codex-team-skill`

Run:

```bash
codex exec "Use $skill-installer. Install skill from GitHub URL: https://github.com/akshaynanavati/codex-team-skill/tree/main/team"
```

After installation, restart Codex so the new skill is loaded.

## How To Interact With This Skill

Use Codex as the primary interface.

- Preferred: ask Codex to `create`, `recruit`, or `execute` using the Team skill
- Secondary: run Python CLIs directly only for debugging, verification, or recovery

In normal usage, you should not need to call the Python scripts manually.

## Quick Start

### 1) Create a Team (via Codex)

```bash
codex exec "Use $team in create mode. Create team 'demo' with mission: Ship reliable weekly customer reporting."
```

This creates:

- `TEAM_demo/mission.md`
- `TEAM_demo/members/`
- `TEAM_demo/state/`
- `TEAM_demo/ceo`
- `TEAM_demo/run.py`

You can also do this from an interactive Codex chat by saying:

- "Use `$team` in create mode and create team `demo` with mission `...`"

### 2) Recruit Teammates (via Codex)

```bash
codex exec "Use $team in recruit mode. Recruit member 'analyst' into team 'demo' with role: Own KPI analysis, investigate anomalies, and escalate blockers quickly."
codex exec "Use $team in recruit mode. Recruit member 'pm' into team 'demo' with role: Prioritize work, resolve dependencies, and report progress to CEO."
```

This creates one folder per member:

- `TEAM_demo/members/analyst/ROLE.md`
- `TEAM_demo/members/analyst/context/`
- `TEAM_demo/members/pm/ROLE.md`
- `TEAM_demo/members/pm/context/`

### 3) Execute Work Rounds (via Codex)

Run one member round:

```bash
codex exec "Use $team in execute mode. Execute one work round for member 'analyst' in team 'demo'."
```

Run all runnable members with the team scheduler:

```bash
python3 TEAM_demo/run.py
```

The runner evaluates each member and invokes Codex for runnable members.

Useful options:

```bash
python3 TEAM_demo/run.py --dry-run
python3 TEAM_demo/run.py --rounds 3
python3 TEAM_demo/run.py --member analyst --sequential
```

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

1. View tasks by member
2. View all tasks
3. View messages for any member
4. View all messages
5. View CEO inbox
6. Respond to a message
7. Unarchive a member message
8. Send a message to a member

### Inbox and Status Behavior

- New messages start as `unread`.
- Opening a message marks it `read`.
- After opening a message, the UI prompts to archive it.
- Archiving sets status to `archived` and removes it from normal inbox views.
- Unarchive (menu option `7`) restores `archived` messages to `read`.

### CEO Escalations and Scheduler Gate

Escalation flow:

1. A member escalates by sending a message to receiver `ceo` (usually during execute mode when blocked/ambiguous).
2. Before each `run.py` scheduler round, unread CEO messages are checked.
3. If unread CEO messages exist, scheduler pauses and prompts for human intervention.
4. CEO uses `./TEAM_<name>/ceo` (options `5` and `6`) to review and respond.
5. Once CEO unread count is cleared, scheduler can continue.

Notes:

- The scheduler gate checks `unread` only. Reading a CEO message clears the unread state; archiving is optional.
- In non-interactive runs, the gate cannot prompt and the scheduler exits with failure until the CEO inbox is handled.

## Complete Example: Build and Operate a 4-Member Team

This example creates one team with four members (max shown here), then runs and manages work using `run.py` and the human CEO CLI.

### 1) Create the Team

```bash
codex exec "Use $team in create mode. Create team 'launch_ops' with mission: Plan and execute a reliable product launch with clear ownership, fast escalation, and weekly reporting."
```

What this does:

- Creates `TEAM_launch_ops/` with mission, members/state directories, `run.py`, and `ceo` wrapper.
- Initializes the runtime SQLite database used by tasks/messages.

### 2) Recruit Four Members (via Codex)

```bash
codex exec "Use $team in recruit mode. Recruit member 'pm' into team 'launch_ops' with role: Own launch plan, prioritize work, and coordinate dependencies across all members."
codex exec "Use $team in recruit mode. Recruit member 'analyst' into team 'launch_ops' with role: Track launch metrics, investigate anomalies, and escalate blockers to CEO quickly."
codex exec "Use $team in recruit mode. Recruit member 'engineer' into team 'launch_ops' with role: Deliver technical launch work, report risks early, and keep task state current."
codex exec "Use $team in recruit mode. Recruit member 'qa' into team 'launch_ops' with role: Validate release quality, triage defects, and escalate release-stopping issues immediately."
```

What this does:

- Creates `ROLE.md` and `context/` for each member under `TEAM_launch_ops/members/`.

### 3) Seed Initial Work from the Human CEO Console

Open the CEO CLI:

```bash
./TEAM_launch_ops/ceo
```

In the menu:

1. Choose `8) Send a message to a member` and send kickoff messages to `pm`, `analyst`, `engineer`, and `qa`.
2. Use `5) View CEO inbox` to monitor escalations coming back to CEO.
3. Use `6) Respond to a message` to answer escalations and unblock work.

### 4) Preview Which Members Will Run

```bash
python3 TEAM_launch_ops/run.py --dry-run
```

What this does:

- Evaluates each member's run criteria.
- Prints runnable members and planned `codex exec` calls without running them.

### 5) Execute Scheduler Rounds

Run one full round (concurrent by default):

```bash
python3 TEAM_launch_ops/run.py --rounds 1
```

Run two rounds sequentially (easier to observe in order):

```bash
python3 TEAM_launch_ops/run.py --rounds 2 --sequential
```

### 6) Handle Escalations During Runs

If `run.py` pauses because CEO has unread messages:

1. Open the CEO CLI in another terminal: `./TEAM_launch_ops/ceo`
2. Choose `5) View CEO inbox` and open unread messages.
3. Choose `6) Respond to a message` when a reply is needed.
4. Return to the paused runner and continue.

### 7) Ongoing Management Commands

Run only specific members:

```bash
python3 TEAM_launch_ops/run.py --member pm --member engineer --rounds 1 --sequential
```

Run with explicit model/effort:

```bash
python3 TEAM_launch_ops/run.py --model gpt-5.3-codex --reasoning-effort medium --rounds 1
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
python3 scripts/team_fs.py --base <dir> create --name <team-name> --mission "<mission>"
python3 scripts/team_fs.py --base <dir> recruit --team <team-name-or-path> --name <member-name> --role "<role>"
```

Messages:

```bash
python3 scripts/team_cli.py --base <dir> --team <team> message send --sender <sender> --receiver <receiver> --body "<text>" [--subject "<subject>"] [--task-id <uuid>]
python3 scripts/team_cli.py --base <dir> --team <team> message list --member <member> [--status inbox|unread|read|archived|all]
python3 scripts/team_cli.py --base <dir> --team <team> message read --member <member> --message-id <uuid>
python3 scripts/team_cli.py --base <dir> --team <team> message archive --member <member> --message-id <uuid>
python3 scripts/team_cli.py --base <dir> --team <team> message list-archived --member <member>
```

Tasks:

```bash
python3 scripts/team_cli.py --base <dir> --team <team> task create --owner <member> --body "<task>" [--priority <int>] [--created-by <actor>]
python3 scripts/team_cli.py --base <dir> --team <team> task list [--owner <member>] [--state open|all|todo|in_progress|blocked|done|cancelled]
python3 scripts/team_cli.py --base <dir> --team <team> task show --task-id <uuid>
python3 scripts/team_cli.py --base <dir> --team <team> task update-state --task-id <uuid> --state <state> [--reason "<reason>"]
```

Use `--json` on `team_cli.py` commands for machine-readable output while debugging.

## Execution Model

The skill defines three exclusive operating modes per run:

1. `create`
2. `recruit`
3. `execute`

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
  - `team_cli.py init/message/task` flows
  - runner `--dry-run` behavior
