# Create Mode

Use this file only for `create` mode.

## Load Only These References

- Load [create-commands.md](create-commands.md) before running any CLI command.
- Load [state-and-templates.md](state-and-templates.md) only when validating scaffolded files, placeholders, or directory structure.

## Goal

Initialize one new `TEAM_<name>/` workspace without recruiting members.

## Required Sequence

1. Confirm the requested team name is valid for `TEAM_<name>/`.
2. Run the team scaffolding command from [create-commands.md](create-commands.md).
3. Write `mission.md` from the provided mission text.
4. If mission text is missing, keep the scaffolded placeholder and ask for mission details.
5. Write `guidelines.md` from the provided team-wide rules.
6. If guidelines are missing, keep the scaffolded placeholder and ask for guidelines details.
7. Initialize the runtime DB schema with the runtime `init` command from [create-commands.md](create-commands.md).
8. Verify the scaffolded layout with [state-and-templates.md](state-and-templates.md).

## Hard Constraints

- Do not recruit members in this mode.
- Do not hand-edit runtime SQLite state.
