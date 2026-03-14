# Recruit Commands

Use this file only for `recruit` mode.

## Environment

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export TEAM_FS_CLI="$CODEX_HOME/skills/team/scripts/team_fs.py"
```

## Recruit One Member

```bash
python3 "$TEAM_FS_CLI" --base "<directory>" recruit --team "<team-name-or-path>" --name "<member-name>" --role "<role text>"
```

## Notes

- `team_fs.py recruit` does not support `--json`.
