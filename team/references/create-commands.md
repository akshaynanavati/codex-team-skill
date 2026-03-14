# Create Commands

Use this file only for `create` mode.

## Environment

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export TEAM_FS_CLI="$CODEX_HOME/skills/team/scripts/team_fs.py"
export TEAM_RUNTIME_CLI="$CODEX_HOME/skills/team/scripts/team_cli.py"
```

## Create Team Workspace

```bash
python3 "$TEAM_FS_CLI" --base "<directory>" create --name "<team-name>" --mission "<mission text>" [--guidelines "<team rules>"]
```

## Initialize Runtime DB

```bash
python3 "$TEAM_RUNTIME_CLI" --base "<directory>" --team "<team-name-or-path>" init
```

## Notes

- Add top-level `--json` for machine-readable output when needed.
