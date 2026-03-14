# State and Templates Reference

Use this file when validating scaffolded outputs, runtime state expectations, or placeholder content.

## Team layout after `create`

- `TEAM_<name>/`
- `TEAM_<name>/members/`
- `TEAM_<name>/state/`
- `TEAM_<name>/mission.md`
- `TEAM_<name>/guidelines.md`
- `TEAM_<name>/ceo`
- `TEAM_<name>/run`

Optional scheduler control file:

- `TEAM_<name>/.stop` causes `TEAM_<name>/run` to stop cleanly at the start of the next round.

## Member layout after `recruit`

- `TEAM_<name>/members/<member-name>/`
- `TEAM_<name>/members/<member-name>/ROLE.md`
- `TEAM_<name>/members/<member-name>/context/`

## Context expectations

- `context/` stores durable, role-relevant memory that should help the member on future runs.
- Prefer small topical files over one large catch-all note.
- Do not use `context/` as an append-only run log; use `state/<member>-last-run.md` for per-run summaries.

## Runtime state location

- SQLite path: `TEAM_<team-name>/state/team_state.sqlite3`
- Assume concurrent workers; runtime CLI handles WAL mode, busy timeout, and write retries.

## Runtime core tables

- `messages`: `message_id`, `sender`, `receiver`, `subject`, `body`, `created_at`, `status`, `read_at`, `archived_at`, optional `task_id`
- `tasks`: `task_id`, `owner`, `state`, `body`, `priority`, `created_by`, `created_at`, `updated_at`, `blocked_reason`

Status and state values:

- Message `status`: `unread|read|archived`
- Task `state`: `todo|in_progress|blocked|done|cancelled`

## Minimal templates

`mission.md`:

```markdown
# Mission
<mission text>
```

`guidelines.md`:

```markdown
# Team Guidelines
<team-wide rules every member must follow>
```

`ROLE.md`:

```markdown
# Role
<member role and operating constraints>
```
