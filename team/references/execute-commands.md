# Execute Commands

Use this file only for `execute` mode.

## Environment

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export TEAM_RUNTIME_CLI="$CODEX_HOME/skills/team/scripts/team_cli.py"
```

## Initialize Runtime DB If Needed

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" init
```

If you need JSON from `team_cli.py`, place `--json` before `init`, `message`, or `task`:

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" --json task list --owner "<member>"
```

## Message Commands

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

## Task Commands

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

## Notes

- For every `team_cli.py` command in this file, put `--json` before the subcommand (`init`, `message`, or `task`) when you need machine-readable output.
- Require `--reason` when setting task state to `blocked`.
- Use only CLI-generated IDs; never fabricate UUIDs.
