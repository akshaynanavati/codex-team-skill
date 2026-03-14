# Train Commands

Use this file only for `train` mode.

## Environment

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export TEAM_FS_CLI="$CODEX_HOME/skills/team/scripts/team_fs.py"
export TEAM_RUNTIME_CLI="$CODEX_HOME/skills/team/scripts/team_cli.py"
```

## Generate Training Snapshot

```bash
python3 "$TEAM_FS_CLI" --base "<directory>" train --team "<team-name-or-path>" --name "<member-name>" [--task-limit <n>] [--message-limit <n>] [--correspondent-limit <n>] [--json]
```

## Inspect Same-Member Runtime State

List tasks:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task list --owner "<member>" [--state open|all|todo|in_progress|blocked|done|cancelled] [--limit <n>]
```

Show one task:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" task show --task-id "<task-uuid>"
```

List inbox messages:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message list --member "<member>" [--status inbox|unread|read|archived|all] [--sender "<sender>"] [--limit <n>]
```

Read one message:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" message read --member "<member>" --message-id "<message-uuid>"
```

## Notes

- Use only CLI-generated IDs; never fabricate UUIDs.
- Use `--json` when the snapshot or runtime output needs machine-readable parsing.
