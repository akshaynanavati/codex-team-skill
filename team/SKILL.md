---
name: team
description: "Create and operate filesystem-based teams in exactly one mode per run: (1) create a team workspace, (2) recruit a member, (3) optimize one member's durable context, (4) train one member by refining `ROLE.md` from task/message evidence, or (5) execute one work round for a specific member. Use when asked to initialize a `TEAM_team-name/` workspace with `members/`, `state/`, `mission.md`, and `guidelines.md`, add `members/member-name/ROLE.md` plus `context/`, review one member's role/context/task/message state and clean the context into concise high-fidelity files, inspect one member's role plus tasks and teammate messages to rewrite `ROLE.md`, or run a mission-aligned member cycle with strict message isolation and SQLite-backed message/task state through the bundled team CLI."
---

# Team

Run exactly one mode per invocation: `create`, `recruit`, `optimize`, `train`, or `execute`.

## Mode Router (Required First Step)

Choose mode before any filesystem write.

- `create`: initialize one new team workspace, then open [references/create-mode.md](references/create-mode.md).
- `recruit`: add one member to an existing team, then open [references/recruit-mode.md](references/recruit-mode.md).
- `optimize`: clean and reorganize one member's durable context, then open [references/optimize-mode.md](references/optimize-mode.md).
- `train`: refine one member's `ROLE.md` from runtime evidence, then open [references/train-mode.md](references/train-mode.md).
- `execute`: run one work round for one member, then open [references/execute-mode.md](references/execute-mode.md).

If intent is ambiguous, ask one clarifying question and stop.

## Global Rules

- Use the invocation directory as default `--base`.
- Enforce team path format: `TEAM_<team-name>/`.
- Enforce member path format: `TEAM_<team-name>/members/<member-name>/`.
- Reject names containing `/` or `\`.
- Require names to match `^[A-Za-z0-9._-]+$`.
- Use scripts for deterministic writes and state transitions.
- Do not hand-edit SQLite state when an equivalent CLI command exists.
- Never run `team_ceo_cli.py` from an agent invocation; reserve it for human terminal usage.

## IDs and Traceability

- Preserve `message_id` and `task_id` exactly as generated.
- Include relevant IDs in replies, task updates, and escalations.
- Include `task_id` in escalation messages when escalation is task-driven.
