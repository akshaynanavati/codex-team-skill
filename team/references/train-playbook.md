# Train Playbook

Use this file only for `train` mode.

## Goal

Refine one member's `ROLE.md` using evidence from:

- the current role definition
- that member's task history
- messages between that member and other teammates

## Required Sequence

1. Read `ROLE.md` first.
2. Run the training inspection command from [commands.md](commands.md).
3. Review:
   - current role text
   - task counts and recent tasks for the member
   - top correspondents and recent cross-member messages
4. Infer stable responsibilities, collaboration patterns, and escalation expectations from the evidence.
5. Rewrite `ROLE.md` so it better matches the actual work the member has been doing.

## Editing Rules

- Edit only `members/<member>/ROLE.md` unless the user explicitly asks for broader changes.
- Keep the role concise and durable.
- Preserve important constraints already present in the role unless the evidence clearly contradicts them.
- Prefer responsibilities and collaboration expectations over transient task details.
- Do not copy message transcripts into the role.
- Do not mutate task or message state in this mode unless the user explicitly asks.

## Evidence Standard

- Use repeated task patterns as stronger evidence than one-off tasks.
- Use repeated message patterns with other members to identify handoff expectations and communication responsibilities.
- Treat blocked tasks and escalation messages as evidence for where the role needs clearer boundaries or escalation rules.
- If runtime state is missing, report the blocker and do not fabricate training evidence.
