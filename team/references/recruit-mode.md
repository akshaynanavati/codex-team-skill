# Recruit Mode

Use this file only for `recruit` mode.

## Load Only These References

- Load [recruit-commands.md](recruit-commands.md) before running any CLI command.
- Load [state-and-templates.md](state-and-templates.md) only when validating scaffolded files, placeholders, or directory structure.

## Goal

Add one member to an existing team and scaffold that member's durable workspace.

## Required Sequence

1. Confirm the target team directory already exists.
2. Confirm the requested member name is valid for `members/<member-name>/`.
3. Run the member scaffolding command from [recruit-commands.md](recruit-commands.md).
4. Write `ROLE.md` exactly from the provided role text.
5. If role text is missing, keep the scaffolded placeholder and ask for role details.
6. Verify the scaffolded layout with [state-and-templates.md](state-and-templates.md).

## Hard Constraints

- Do not create or edit other members in this mode.
- Do not hand-edit runtime SQLite state.
