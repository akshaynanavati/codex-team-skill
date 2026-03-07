# State and Templates Reference

Use this file when validating scaffolded outputs, runtime state expectations, or placeholder content.

## Team layout after `create`

- `TEAM_<name>/`
- `TEAM_<name>/members/`
- `TEAM_<name>/state/`
- `TEAM_<name>/mission.md`
- `TEAM_<name>/ceo`
- `TEAM_<name>/run`

## Member layout after `recruit`

- `TEAM_<name>/members/<member-name>/`
- `TEAM_<name>/members/<member-name>/ROLE.md`
- `TEAM_<name>/members/<member-name>/context/`

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

`ROLE.md`:

```markdown
# Role
<member role and operating constraints>
```
