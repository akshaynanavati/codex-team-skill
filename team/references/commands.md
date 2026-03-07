# Team Commands Reference

Use this file after selecting a mode in `SKILL.md`.

## Table of Contents

- Script environment setup
- `create` mode commands
- `recruit` mode commands
- Runtime DB initialization
- Runtime message commands
- Runtime task commands
- CEO console (human only)
- JSON and state notes

## Script environment setup

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export TEAM_FS_CLI="$CODEX_HOME/skills/team/scripts/team_fs.py"
export TEAM_RUNTIME_CLI="$CODEX_HOME/skills/team/scripts/team_cli.py"
export TEAM_CEO_CLI="$CODEX_HOME/skills/team/scripts/team_ceo_cli.py"
```

## `create` mode commands

Create team workspace:

```bash
python3 "$TEAM_FS_CLI" --base "<directory>" create --name "<team-name>" --mission "<mission text>"
```

Then initialize runtime DB schema:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" init
```

## `recruit` mode commands

Recruit one member:

```bash
python3 "$TEAM_FS_CLI" --base "<directory>" recruit --team "<team-name-or-path>" --name "<member-name>" --role "<role text>"
```

## Runtime DB initialization

Initialize if missing (safe idempotent behavior depends on CLI implementation):

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" init
```

## Runtime message commands

Send:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message send --sender "<sender>" --receiver "<receiver-or-ceo>" --body "<message>" [--subject "<subject>"] [--task-id "<task-uuid>"]
```

List inbox or filtered messages:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message list --member "<member>" [--status inbox|unread|read|archived|all] [--sender "<sender>"] [--limit <n>]
```

Read one message:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message read --member "<member>" --message-id "<message-uuid>"
```

Archive one message:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message archive --member "<member>" --message-id "<message-uuid>"
```

List archived:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message list-archived --member "<member>" [--limit <n>]
```

## Runtime task commands

Create:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task create --owner "<member>" --body "<task body>" [--state todo|in_progress|blocked|done|cancelled] [--priority <int>] [--created-by "<actor>"]
```

List:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task list [--owner "<member>"] [--state open|all|todo|in_progress|blocked|done|cancelled] [--limit <n>]
```

Show:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task show --task-id "<task-uuid>"
```

Update state:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task update-state --task-id "<task-uuid>" --state "<todo|in_progress|blocked|done|cancelled>" [--reason "<note>"]
```

## CEO console (human only)

Use only in a human terminal session, never in a member agent run:

```bash
python3 "$TEAM_CEO_CLI" --base "<directory>" --team "<team-name-or-path>"
./TEAM_<name>/ceo [extra flags]
```

## JSON and state notes

- Add top-level `--json` for machine-readable output.
- Require `--reason` when setting task state to `blocked`.
- Use only CLI-generated IDs; never fabricate UUIDs.
