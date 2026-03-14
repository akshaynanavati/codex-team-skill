#!/usr/bin/env python3
"""SQLite-backed CLI for team messages and tasks."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

MESSAGE_STATUSES = ("unread", "read", "archived")
MESSAGE_LIST_SCOPES = ("inbox", "unread", "read", "archived", "all")

TASK_STATES = ("todo", "in_progress", "blocked", "done", "cancelled")
TASK_LIST_SCOPES = ("open", "all", *TASK_STATES)

DB_FILENAME = "team_state.sqlite3"
STOP_FILENAME = ".stop"
WRITE_RETRIES = 6
RETRY_BASE_SLEEP_SECONDS = 0.05


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('todo', 'in_progress', 'blocked', 'done', 'cancelled')),
    body TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    blocked_reason TEXT,
    CHECK (length(task_id) = 36)
);

CREATE INDEX IF NOT EXISTS idx_tasks_owner_state_priority_created
ON tasks (owner, state, priority DESC, created_at ASC, task_id ASC);

CREATE INDEX IF NOT EXISTS idx_tasks_state_priority_created
ON tasks (state, priority DESC, created_at ASC, task_id ASC);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    receiver TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('unread', 'read', 'archived')),
    read_at TEXT,
    archived_at TEXT,
    task_id TEXT REFERENCES tasks(task_id),
    CHECK (length(message_id) = 36)
);

CREATE INDEX IF NOT EXISTS idx_messages_receiver_status_created
ON messages (receiver, status, created_at DESC, message_id ASC);

CREATE INDEX IF NOT EXISTS idx_messages_receiver_created
ON messages (receiver, created_at DESC, message_id ASC);

CREATE INDEX IF NOT EXISTS idx_messages_task_id
ON messages (task_id);
"""


def fail(message: str) -> int:
    print(f"[ERROR] {message}", file=sys.stderr)
    return 1


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_identity(raw: str, label: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError(f"{label} cannot be empty.")
    if "/" in value or "\\" in value:
        raise ValueError(f"{label} cannot contain path separators: {raw!r}")
    if not VALID_NAME.match(value):
        raise ValueError(
            f"{label} must match {VALID_NAME.pattern} (letters, numbers, ., _, -)."
        )
    return value.lower()


def normalize_uuid(raw: str, label: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise ValueError(f"{label} must be a UUID: {raw!r}") from exc


def normalize_body(raw: str, label: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError(f"{label} cannot be empty.")
    return value


def resolve_team_root(team: str, base: Path) -> Path:
    team_value = team.strip()
    if not team_value:
        raise ValueError("team cannot be empty.")

    team_path = Path(team_value)
    if team_path.is_absolute():
        return team_path.resolve()

    if len(team_path.parts) > 1 or team_value.startswith("."):
        return (base / team_path).resolve()

    if team_value.startswith("TEAM_"):
        normalized_name = team_value[len("TEAM_") :]
        if not normalized_name:
            raise ValueError("team value 'TEAM_' is invalid.")
        normalize_identity(normalized_name, "team name")
        return (base / team_value).resolve()

    normalize_identity(team_value, "team name")
    return (base / f"TEAM_{team_value}").resolve()


def ensure_team_root(team_root: Path) -> None:
    if not team_root.exists() or not team_root.is_dir():
        raise ValueError(f"team directory not found: {team_root}")


def stop_file_path(team_root: Path) -> Path:
    return team_root / STOP_FILENAME


def ensure_database(team_root: Path) -> tuple[sqlite3.Connection, Path]:
    state_dir = team_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    db_path = state_dir / DB_FILENAME

    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.executescript(SCHEMA_SQL)

    return conn, db_path


def with_write_transaction(conn: sqlite3.Connection, operation: Any) -> Any:
    for attempt in range(WRITE_RETRIES):
        try:
            conn.execute("BEGIN IMMEDIATE")
            result = operation(conn)
            conn.commit()
            return result
        except sqlite3.OperationalError as exc:
            conn.rollback()
            locked = "locked" in str(exc).lower()
            if locked and attempt < WRITE_RETRIES - 1:
                time.sleep(RETRY_BASE_SLEEP_SECONDS * (2**attempt))
                continue
            raise
        except Exception:
            conn.rollback()
            raise
    raise RuntimeError("unreachable retry loop termination")


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def body_preview(body: str, width: int = 72) -> str:
    cleaned = " ".join(body.split())
    if len(cleaned) <= width:
        return cleaned
    return f"{cleaned[: width - 3]}..."


def print_json(data: Any) -> None:
    print(json.dumps(data, sort_keys=True))


def print_message_list(records: list[dict[str, Any]]) -> None:
    print(f"count: {len(records)}")
    print("message_id\tstatus\tsender\treceiver\tcreated_at\tsubject\tbody_preview")
    for record in records:
        print(
            "\t".join(
                [
                    record["message_id"],
                    record["status"],
                    record["sender"],
                    record["receiver"],
                    record["created_at"],
                    record["subject"],
                    body_preview(record["body"]),
                ]
            )
        )


def print_task_list(records: list[dict[str, Any]]) -> None:
    print(f"count: {len(records)}")
    print("task_id\towner\tstate\tpriority\tcreated_at\tupdated_at\tbody_preview")
    for record in records:
        print(
            "\t".join(
                [
                    record["task_id"],
                    record["owner"],
                    record["state"],
                    str(record["priority"]),
                    record["created_at"],
                    record["updated_at"],
                    body_preview(record["body"]),
                ]
            )
        )


def cmd_init(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    message_count = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
    task_count = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
    payload = {
        "team_root": str(args.team_root),
        "db_path": str(args.db_path),
        "messages": message_count,
        "tasks": task_count,
    }

    if args.json:
        print_json(payload)
    else:
        print(f"team_root: {payload['team_root']}")
        print(f"db_path: {payload['db_path']}")
        print(f"messages: {payload['messages']}")
        print(f"tasks: {payload['tasks']}")
    return 0


def cmd_message_send(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        sender = normalize_identity(args.sender, "sender")
        receiver = normalize_identity(args.receiver, "receiver")
        subject = args.subject.strip()
        body = normalize_body(args.body, "body")
        task_id = normalize_uuid(args.task_id, "task-id") if args.task_id else None
    except ValueError as exc:
        return fail(str(exc))

    message_id = str(uuid.uuid4())
    created_at = now_utc_iso()

    def _insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO messages (
                message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'unread', NULL, NULL, ?)
            """,
            (message_id, sender, receiver, subject, body, created_at, task_id),
        )

    with_write_transaction(conn, _insert)
    row = conn.execute(
        "SELECT * FROM messages WHERE message_id = ?",
        (message_id,),
    ).fetchone()

    if row is None:
        return fail("failed to load inserted message.")

    payload = row_dict(row)
    if args.json:
        print_json(payload)
    else:
        print("message_sent: true")
        for key in ("message_id", "sender", "receiver", "status", "created_at", "task_id"):
            print(f"{key}: {payload.get(key) or ''}")
    return 0


def query_message_rows(
    conn: sqlite3.Connection,
    member: str,
    status_scope: str,
    sender: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    clauses = ["receiver = ?"]
    params: list[Any] = [member]

    if status_scope == "inbox":
        clauses.append("status IN ('unread', 'read')")
    elif status_scope != "all":
        clauses.append("status = ?")
        params.append(status_scope)

    if sender is not None:
        clauses.append("sender = ?")
        params.append(sender)

    params.append(limit)
    where_clause = " AND ".join(clauses)

    return conn.execute(
        f"""
        SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
        FROM messages
        WHERE {where_clause}
        ORDER BY created_at DESC, message_id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()


def cmd_message_list(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        member = normalize_identity(args.member, "member")
        sender = normalize_identity(args.sender, "sender") if args.sender else None
    except ValueError as exc:
        return fail(str(exc))

    rows = query_message_rows(
        conn=conn,
        member=member,
        status_scope=args.status,
        sender=sender,
        limit=args.limit,
    )
    records = [row_dict(row) for row in rows]
    if args.json:
        print_json(records)
    else:
        print_message_list(records)
    return 0


def cmd_message_list_archived(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        member = normalize_identity(args.member, "member")
    except ValueError as exc:
        return fail(str(exc))

    rows = query_message_rows(
        conn=conn,
        member=member,
        status_scope="archived",
        sender=None,
        limit=args.limit,
    )
    records = [row_dict(row) for row in rows]
    if args.json:
        print_json(records)
    else:
        print_message_list(records)
    return 0


def cmd_message_read(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        member = normalize_identity(args.member, "member")
        message_id = normalize_uuid(args.message_id, "message-id")
    except ValueError as exc:
        return fail(str(exc))

    result: dict[str, Any] = {"record": None}

    def _read(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            """
            SELECT * FROM messages
            WHERE message_id = ? AND receiver = ?
            """,
            (message_id, member),
        ).fetchone()

        if row is None:
            return

        if row["status"] == "unread":
            read_at = now_utc_iso()
            connection.execute(
                """
                UPDATE messages
                SET status = 'read', read_at = ?, archived_at = NULL
                WHERE message_id = ?
                """,
                (read_at, message_id),
            )

        fresh = connection.execute(
            "SELECT * FROM messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        result["record"] = row_dict(fresh) if fresh is not None else None

    with_write_transaction(conn, _read)
    record = result["record"]
    if record is None:
        return fail(f"message not found for member '{member}': {message_id}")

    if args.json:
        print_json(record)
    else:
        for key in (
            "message_id",
            "sender",
            "receiver",
            "status",
            "created_at",
            "read_at",
            "archived_at",
            "task_id",
            "subject",
            "body",
        ):
            print(f"{key}: {record.get(key) or ''}")
    return 0


def cmd_message_archive(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        member = normalize_identity(args.member, "member")
        message_id = normalize_uuid(args.message_id, "message-id")
    except ValueError as exc:
        return fail(str(exc))

    result: dict[str, Any] = {"record": None}

    def _archive(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT * FROM messages WHERE message_id = ? AND receiver = ?",
            (message_id, member),
        ).fetchone()
        if row is None:
            return

        archived_at = now_utc_iso()
        read_at = row["read_at"] if row["read_at"] else archived_at
        connection.execute(
            """
            UPDATE messages
            SET status = 'archived', archived_at = ?, read_at = ?
            WHERE message_id = ? AND receiver = ?
            """,
            (archived_at, read_at, message_id, member),
        )
        updated = connection.execute(
            "SELECT * FROM messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        result["record"] = row_dict(updated) if updated is not None else None

    with_write_transaction(conn, _archive)
    record = result["record"]
    if record is None:
        return fail(f"message not found for member '{member}': {message_id}")

    if args.json:
        print_json(record)
    else:
        print(f"message_archived: {record['message_id']}")
        print(f"status: {record['status']}")
        print(f"archived_at: {record.get('archived_at') or ''}")
    return 0


def cmd_task_create(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        owner = normalize_identity(args.owner, "owner")
        created_by = normalize_identity(args.created_by, "created-by") if args.created_by else None
        body = normalize_body(args.body, "body")
    except ValueError as exc:
        return fail(str(exc))

    task_id = str(uuid.uuid4())
    timestamp = now_utc_iso()

    def _insert(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO tasks (
                task_id, owner, state, body, priority, created_by, created_at, updated_at, blocked_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                task_id,
                owner,
                args.state,
                body,
                args.priority,
                created_by,
                timestamp,
                timestamp,
            ),
        )

    with_write_transaction(conn, _insert)
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        return fail("failed to load inserted task.")

    payload = row_dict(row)
    if args.json:
        print_json(payload)
    else:
        print("task_created: true")
        for key in ("task_id", "owner", "state", "priority", "created_at", "updated_at"):
            print(f"{key}: {payload.get(key) or ''}")
    return 0


def query_task_rows(
    conn: sqlite3.Connection,
    owner: str | None,
    state_scope: str,
    limit: int,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []

    if owner is not None:
        clauses.append("owner = ?")
        params.append(owner)

    if state_scope == "open":
        clauses.append("state IN ('todo', 'in_progress', 'blocked')")
    elif state_scope != "all":
        clauses.append("state = ?")
        params.append(state_scope)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    return conn.execute(
        f"""
        SELECT task_id, owner, state, body, priority, created_by, created_at, updated_at, blocked_reason
        FROM tasks
        {where_clause}
        ORDER BY priority DESC, created_at ASC, task_id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()


def cmd_task_list(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        owner = normalize_identity(args.owner, "owner") if args.owner else None
    except ValueError as exc:
        return fail(str(exc))

    rows = query_task_rows(
        conn=conn,
        owner=owner,
        state_scope=args.state,
        limit=args.limit,
    )
    records = [row_dict(row) for row in rows]
    if args.json:
        print_json(records)
    else:
        print_task_list(records)
    return 0


def cmd_task_show(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        task_id = normalize_uuid(args.task_id, "task-id")
    except ValueError as exc:
        return fail(str(exc))

    row = conn.execute(
        """
        SELECT task_id, owner, state, body, priority, created_by, created_at, updated_at, blocked_reason
        FROM tasks
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchone()
    if row is None:
        return fail(f"task not found: {task_id}")

    payload = row_dict(row)
    if args.json:
        print_json(payload)
    else:
        for key in (
            "task_id",
            "owner",
            "state",
            "priority",
            "created_by",
            "created_at",
            "updated_at",
            "blocked_reason",
            "body",
        ):
            print(f"{key}: {payload.get(key) or ''}")
    return 0


def cmd_task_update_state(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    try:
        task_id = normalize_uuid(args.task_id, "task-id")
        reason = args.reason.strip() if args.reason else None
    except ValueError as exc:
        return fail(str(exc))

    if args.state == "blocked" and not reason:
        return fail("--reason is required when setting state to 'blocked'.")

    result: dict[str, Any] = {"record": None}
    updated_at = now_utc_iso()

    def _update(connection: sqlite3.Connection) -> None:
        existing = connection.execute(
            "SELECT task_id FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if existing is None:
            return

        if args.state == "blocked":
            blocked_reason = reason
        elif reason:
            blocked_reason = reason
        else:
            blocked_reason = None

        connection.execute(
            """
            UPDATE tasks
            SET state = ?, updated_at = ?, blocked_reason = ?
            WHERE task_id = ?
            """,
            (args.state, updated_at, blocked_reason, task_id),
        )
        updated = connection.execute(
            """
            SELECT task_id, owner, state, body, priority, created_by, created_at, updated_at, blocked_reason
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        result["record"] = row_dict(updated) if updated is not None else None

    with_write_transaction(conn, _update)

    record = result["record"]
    if record is None:
        return fail(f"task not found: {task_id}")

    if args.json:
        print_json(record)
    else:
        print(f"task_updated: {record['task_id']}")
        print(f"state: {record['state']}")
        print(f"updated_at: {record['updated_at']}")
        print(f"blocked_reason: {record.get('blocked_reason') or ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Team CLI for SQLite-backed messages and tasks."
    )
    parser.add_argument(
        "--base",
        default=".",
        help="Base directory used when --team is a relative name/path (default: current directory).",
    )
    parser.add_argument(
        "--team",
        required=True,
        help="Team name, TEAM_<name>, or path to a team directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON for command output.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize or verify the SQLite database schema for this team.",
    )
    init_parser.set_defaults(func=cmd_init)

    message_parser = subparsers.add_parser("message", help="Manage messages.")
    message_sub = message_parser.add_subparsers(dest="message_command", required=True)

    message_send = message_sub.add_parser("send", help="Send a message.")
    message_send.add_argument("--sender", required=True, help="Sender identity.")
    message_send.add_argument("--receiver", required=True, help="Receiver identity (e.g. member or ceo).")
    message_send.add_argument("--subject", default="", help="Optional short subject.")
    message_send.add_argument("--body", required=True, help="Message body.")
    message_send.add_argument(
        "--task-id",
        help="Optional task UUID linked to this message.",
    )
    message_send.set_defaults(func=cmd_message_send)

    message_list = message_sub.add_parser("list", help="List messages for one member inbox.")
    message_list.add_argument("--member", required=True, help="Inbox owner (receiver).")
    message_list.add_argument(
        "--status",
        default="inbox",
        choices=MESSAGE_LIST_SCOPES,
        help="Filter by status scope (default: inbox = unread + read).",
    )
    message_list.add_argument("--sender", help="Optional sender filter.")
    message_list.add_argument("--limit", type=int, default=50, help="Maximum rows (default: 50).")
    message_list.set_defaults(func=cmd_message_list)

    message_read = message_sub.add_parser("read", help="Read one message by ID.")
    message_read.add_argument("--member", required=True, help="Inbox owner (receiver).")
    message_read.add_argument("--message-id", required=True, help="Message UUID.")
    message_read.set_defaults(func=cmd_message_read)

    message_archive = message_sub.add_parser("archive", help="Archive one message by ID.")
    message_archive.add_argument("--member", required=True, help="Inbox owner (receiver).")
    message_archive.add_argument("--message-id", required=True, help="Message UUID.")
    message_archive.set_defaults(func=cmd_message_archive)

    message_archived = message_sub.add_parser(
        "list-archived",
        help="List archived messages for one member.",
    )
    message_archived.add_argument("--member", required=True, help="Inbox owner (receiver).")
    message_archived.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum rows (default: 50).",
    )
    message_archived.set_defaults(func=cmd_message_list_archived)

    task_parser = subparsers.add_parser("task", help="Manage tasks.")
    task_sub = task_parser.add_subparsers(dest="task_command", required=True)

    task_create = task_sub.add_parser("create", help="Create a task.")
    task_create.add_argument("--owner", required=True, help="Task owner.")
    task_create.add_argument(
        "--state",
        default="todo",
        choices=TASK_STATES,
        help="Initial task state (default: todo).",
    )
    task_create.add_argument("--priority", type=int, default=0, help="Task priority (higher first).")
    task_create.add_argument("--created-by", help="Optional creator identity.")
    task_create.add_argument("--body", required=True, help="Task body.")
    task_create.set_defaults(func=cmd_task_create)

    task_list = task_sub.add_parser("list", help="List tasks.")
    task_list.add_argument("--owner", help="Optional owner filter.")
    task_list.add_argument(
        "--state",
        default="open",
        choices=TASK_LIST_SCOPES,
        help="Filter by state scope (default: open = todo + in_progress + blocked).",
    )
    task_list.add_argument("--limit", type=int, default=50, help="Maximum rows (default: 50).")
    task_list.set_defaults(func=cmd_task_list)

    task_show = task_sub.add_parser("show", help="Show one task by ID.")
    task_show.add_argument("--task-id", required=True, help="Task UUID.")
    task_show.set_defaults(func=cmd_task_show)

    task_update_state = task_sub.add_parser("update-state", help="Update task state.")
    task_update_state.add_argument("--task-id", required=True, help="Task UUID.")
    task_update_state.add_argument("--state", required=True, choices=TASK_STATES, help="New state.")
    task_update_state.add_argument(
        "--reason",
        help="Required when state=blocked. Optional note for other states.",
    )
    task_update_state.set_defaults(func=cmd_task_update_state)

    return parser


def normalize_global_flag_order(argv: list[str]) -> list[str]:
    """Allow global flags like --json to appear after subcommands."""
    if "--json" not in argv:
        return argv

    reordered = ["--json"]
    reordered.extend(arg for arg in argv if arg != "--json")
    return reordered


def main() -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_global_flag_order(sys.argv[1:]))

    base = Path(args.base).resolve()

    try:
        team_root = resolve_team_root(args.team, base)
        ensure_team_root(team_root)
    except ValueError as exc:
        return fail(str(exc))

    try:
        conn, db_path = ensure_database(team_root)
    except sqlite3.Error as exc:
        return fail(f"failed to initialize database: {exc}")

    args.team_root = team_root
    args.db_path = db_path

    try:
        return args.func(args, conn)
    except sqlite3.IntegrityError as exc:
        return fail(f"database integrity error: {exc}")
    except sqlite3.OperationalError as exc:
        return fail(f"database operational error: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
