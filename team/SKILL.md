---
name: team
description: "Create and operate filesystem-based teams in exactly one mode per run: (1) create a team workspace, (2) recruit a member, (3) optimize one member's durable context, (4) train one member by refining `ROLE.md` from task/message evidence, or (5) execute one work round for a specific member. Use when asked to initialize `TEAM_<name>/` with `members/`, `state/`, `mission.md`, and `guidelines.md`, add `members/<name>/ROLE.md` plus `context/`, review one member's role/context/task/message state and clean the context into concise high-fidelity files, inspect one member's role plus tasks and teammate messages to rewrite `ROLE.md`, or run a mission-aligned member cycle with strict message isolation and SQLite-backed message/task state through the bundled team CLI."
---

# Team

Run exactly one mode per invocation: `create`, `recruit`, `optimize`, `train`, or `execute`.

## Load References Progressively

- Load [references/commands.md](references/commands.md) after selecting a mode and before running any CLI command.
- Load [references/optimize-playbook.md](references/optimize-playbook.md) only for `optimize` mode.
- Load [references/train-playbook.md](references/train-playbook.md) only for `train` mode.
- Load [references/execute-playbook.md](references/execute-playbook.md) only for `execute` mode.
- Load [references/state-and-templates.md](references/state-and-templates.md) when validating scaffolded files, runtime schema expectations, or directory structure.

## Mode Router (Required First Step)

Choose mode before any filesystem write.

- `create`: initialize one new team workspace.
- `recruit`: add one member to an existing team.
- `optimize`: clean and reorganize one member's durable context.
- `train`: refine one member's `ROLE.md` from their actual work patterns.
- `execute`: run one work round for one member.

If intent is ambiguous, ask one clarifying question and stop.

## Global Rules

- Use the invocation directory as default `--base`.
- Enforce team path format: `TEAM_<team-name>/`.
- Enforce member path format: `TEAM_<team-name>/members/<member-name>/`.
- Reject names containing `/` or `\`.
- Require names to match `^[A-Za-z0-9._-]+$`.
- Set `CODEX_HOME`, `TEAM_FS_CLI`, `TEAM_RUNTIME_CLI`, and `TEAM_CEO_CLI` using [references/commands.md](references/commands.md).
- Use scripts for deterministic writes and state transitions.
- Do not hand-edit SQLite state when an equivalent CLI command exists.
- Allow member runs to list/read/archive only the active member inbox.
- Never read another member inbox during member runs.
- Never read CEO inbox during normal member runs.
- Allow sending escalation messages with `--receiver ceo`.
- Never run `team_ceo_cli.py` from an agent invocation; reserve it for human terminal usage.

## Mode: Create

Use only when asked to create a team.

- Run team scaffolding command from [references/commands.md](references/commands.md).
- Write `mission.md` from provided mission text.
- If mission text is missing, write a short placeholder and ask for mission details.
- Write `guidelines.md` with provided team-wide rules.
- If guidelines are missing, write a short placeholder and ask for guidelines details.
- Initialize runtime DB schema using the runtime `init` command.
- Verify scaffolded layout using [references/state-and-templates.md](references/state-and-templates.md).
- Do not recruit members in this mode.

## Mode: Recruit

Use only when asked to recruit one member.

- Confirm team directory exists.
- Run member scaffolding command from [references/commands.md](references/commands.md).
- Write `ROLE.md` exactly from provided role text.
- If role text is missing, write a short placeholder and ask for role details.
- Verify scaffolded layout using [references/state-and-templates.md](references/state-and-templates.md).
- Do not create or edit other members in this mode.

## Mode: Execute

Use only when asked to execute one work round for one member.

- Enforce preconditions and run the full phase checklist from [references/execute-playbook.md](references/execute-playbook.md).
- Run phases in strict order: `Task Completion -> Message Processing -> Prioritization -> Close-out`.
- If `guidelines.md` exists, load and follow it.
- Use runtime CLI commands from [references/commands.md](references/commands.md).
- If runtime CLI is unavailable, report blocker and never fabricate state.

## Mode: Optimize

Use only when asked to optimize one member's stored context.

- Enforce the full checklist from [references/optimize-playbook.md](references/optimize-playbook.md).
- Run the optimize inspection command from [references/commands.md](references/commands.md) before editing files.
- Read `ROLE.md` first and treat it as the contract for what durable context should exist.
- Inspect only the active member's tasks and messages when deciding what context is stale or missing.
- Edit only files inside `members/<member>/context/` unless the user explicitly asks for broader changes.
- Prefer multiple small topical files over one large mixed-purpose file.
- Delete or condense stale context that is already represented by closed tasks, archived messages, or obsolete plans.
- Keep context focused on durable, role-relevant information that should improve future runs.
- Do not execute tasks, reply to messages, or mutate task/message state in this mode unless the user explicitly asks.

## Mode: Train

Use only when asked to train one member by updating their role from runtime evidence.

- Enforce the full checklist from [references/train-playbook.md](references/train-playbook.md).
- Run the training inspection command from [references/commands.md](references/commands.md) before editing files.
- Read `ROLE.md` first and treat it as the starting contract, not the final truth.
- Review that member's own tasks and messages between that member and other teammates.
- Use repeated task patterns and repeated collaboration patterns as the main evidence for role changes.
- Edit only `members/<member>/ROLE.md` unless the user explicitly asks for broader changes.
- Keep the updated role concise, durable, and aligned with the member's real responsibilities.
- Do not mutate task or message state in this mode unless the user explicitly asks.

## IDs and Traceability

- Preserve `message_id` and `task_id` exactly as generated.
- Include relevant IDs in replies, task updates, and escalations.
- Include `task_id` in escalation messages when escalation is task-driven.
