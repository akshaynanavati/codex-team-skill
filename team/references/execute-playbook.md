# Execute Mode Playbook

Use this file only for `execute` mode.

## Preconditions

- Ensure `TEAM_<name>/mission.md` exists.
- If `TEAM_<name>/guidelines.md` exists, plan to enforce it.
- Ensure `members/<member>/ROLE.md` exists.
- Ensure `members/<member>/context/` exists; create it if missing.
- Ensure runtime CLI is available before mutating state.

## Step 0: Setup

- Append current UTC timestamp to `members/<member>/.run` (create file if needed).
- Load and follow `mission.md`.
- Load and follow `guidelines.md` when it exists.
- Load and follow `ROLE.md` exactly as written.
- Load only relevant markdown files from `context/`.

## Phase 1: Task Completion

- List open tasks for active member.
- Prioritize `in_progress` tasks before starting new work.
- If no task is `in_progress`, select highest-priority next task.
- If tasks are tightly related, complete them together in one coherent effort.
- Avoid executing unrelated tasks in a single round.
- Minimize leftover `in_progress` tasks.
- If a selected task is ambiguous, conflicting, or not completable, escalate to CEO and set state to `blocked` with reason.

## Phase 2: Message Processing

- List unarchived inbox messages for active member; process unread first.
- Read messages by `message_id`.
- Complete quick actions immediately.
- For non-quick actions, create concrete tasks and include source `message_id`.
- Archive a message only when fully actioned now or when created tasks fully cover follow-up.
- Send required responses during this run when possible.
- If response must happen later, capture the obligation explicitly in task state.

## Phase 3: Prioritization

- Review all member tasks in `todo`, `in_progress`, and `blocked`.
- Cancel stale tasks with reason.
- Merge duplicate tasks and preserve traceability in retained task text.
- Split large tasks into smaller, concrete, single-purpose tasks.
- Reassign priority across the full task set each run.

## Phase 4: Close-out

- Update and clean member context files.
- Write short summary to `state/<member>-last-run.md` with timestamp, handled task IDs, and blockers or escalations.

## Hard Constraints

- Run phases in strict order: `Task Completion -> Message Processing -> Prioritization -> Close-out`.
- Never archive actionable work unless completed now or represented by task records.
- Prefer many small single-purpose tasks over one large task.
- Finish `in_progress` tasks before starting unrelated new work.
- Keep actions mission-aligned.
- Keep actions aligned with team guidelines when `guidelines.md` exists.
- If mission and role conflict, escalate to CEO and mark selected task `blocked`.
- If runtime CLI is unavailable, report blocker and never fabricate state.
- Never read messages not addressed to active member.
- Never modify task state for another member.
