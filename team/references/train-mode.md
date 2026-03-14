# Train Mode

Use this file only for `train` mode.

## Load Only These References

- Load [train-commands.md](train-commands.md) before editing files or inspecting runtime state.

## Goal

Refine one member's `ROLE.md` using evidence from the current role definition, that member's task history, and messages between that member and other teammates.

## Required Sequence

1. Read `ROLE.md` first and treat it as the starting contract, not the final truth.
2. Run the training inspection command from [train-commands.md](train-commands.md).
3. Review the current role text, task counts, recent tasks, top correspondents, and recent cross-member messages.
4. Infer stable responsibilities, collaboration patterns, and escalation expectations from the evidence.
5. Rewrite `ROLE.md` so it better matches the actual work the member has been doing.

## Editing Rules

- Review only that member's own tasks and messages between that member and other teammates.
- Use repeated task patterns and repeated collaboration patterns as the main evidence for role changes.
- Edit only `members/<member>/ROLE.md` unless the user explicitly asks for broader changes.
- Keep the updated role concise, durable, and aligned with the member's real responsibilities.
- Preserve important constraints already present in the role unless the evidence clearly contradicts them.
- Prefer responsibilities and collaboration expectations over transient task details.
- Do not copy message transcripts into the role.

## Evidence Standard

- Use repeated task patterns as stronger evidence than one-off tasks.
- Use repeated message patterns with other members to identify handoff expectations and communication responsibilities.
- Treat blocked tasks and escalation messages as evidence for where the role needs clearer boundaries or escalation rules.
- If runtime state is missing, report the blocker and do not fabricate training evidence.

## Hard Constraints

- Do not mutate task or message state in this mode unless the user explicitly asks.
