#!/usr/bin/env python3
"""Human-only CEO terminal UI for inspecting team state and replying to messages.

This tool is intentionally blocked in Codex agent runtime environments.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable

import team_cli as runtime

TASK_SCOPE_CHOICES = ("open", "all", *runtime.TASK_STATES)
MESSAGE_SCOPE_CHOICES = runtime.MESSAGE_LIST_SCOPES


def fail(message: str) -> int:
    print(f"[ERROR] {message}", file=sys.stderr)
    return 1


def enforce_human_only_runtime() -> None:
    """Deny execution when running under Codex agent infrastructure."""
    codex_markers = ("CODEX_CI", "CODEX_THREAD_ID", "CODEX_SANDBOX")
    if any(os.getenv(marker) for marker in codex_markers):
        raise PermissionError(
            "This CLI is for humans only. Agent execution is permanently blocked."
        )

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise PermissionError("Interactive TTY input/output is required.")


def clear_screen() -> None:
    print("\033[2J\033[H", end="")


def prompt_line(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{label}{suffix}: ").strip()
    if raw:
        return raw
    return default or ""


def prompt_int(label: str, default: int) -> int:
    while True:
        value = prompt_line(label, str(default))
        try:
            parsed = int(value)
        except ValueError:
            print("Enter a valid integer.")
            continue
        if parsed <= 0:
            print("Enter an integer greater than 0.")
            continue
        return parsed


def prompt_scope(label: str, choices: Iterable[str], default: str) -> str:
    options = tuple(choices)
    while True:
        value = prompt_line(f"{label} ({'/'.join(options)})", default).lower()
        if value in options:
            return value
        print(f"Choose one of: {', '.join(options)}")


def prompt_yes_no(label: str, default: bool = False) -> bool:
    choices = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{choices}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Enter y or n.")


def prompt_numbered_selection(label: str, total: int) -> int | None:
    while True:
        raw = input(f"{label} number (1-{total}, blank to return): ").strip()
        if not raw:
            return None
        try:
            selected = int(raw)
        except ValueError:
            print("Enter a valid number.")
            continue
        if selected < 1 or selected > total:
            print(f"Choose a number between 1 and {total}.")
            continue
        return selected - 1


def pause() -> None:
    input("\nPress Enter to continue...")


def prompt_multiline(label: str) -> str:
    print(f"{label} (finish with a line containing only '.')")
    lines: list[str] = []
    while True:
        line = input("> ")
        if line == ".":
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("Message body cannot be empty.")
    return text


def discover_members(conn: sqlite3.Connection, team_root: Path) -> list[str]:
    members: set[str] = set()

    members_dir = team_root / "members"
    if members_dir.is_dir():
        for child in members_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                members.add(runtime.normalize_identity(child.name, "member"))
            except ValueError:
                continue

    for query in (
        "SELECT DISTINCT owner AS identity FROM tasks",
        "SELECT DISTINCT sender AS identity FROM messages",
        "SELECT DISTINCT receiver AS identity FROM messages",
    ):
        for row in conn.execute(query):
            raw = row["identity"]
            if not raw:
                continue
            try:
                members.add(runtime.normalize_identity(str(raw), "identity"))
            except ValueError:
                continue

    return sorted(members)


def prompt_member(conn: sqlite3.Connection, team_root: Path, default: str | None = None) -> str:
    members = discover_members(conn, team_root)
    if members:
        print("\nKnown members:")
        for member in members:
            print(f" - {member}")

    while True:
        member = prompt_line("Member inbox/owner", default).strip()
        if not member:
            print("Member is required.")
            continue
        try:
            return runtime.normalize_identity(member, "member")
        except ValueError as exc:
            print(exc)


def print_header(team_root: Path, db_path: Path) -> None:
    print("Team CEO Console (Human-only)")
    print(f"team: {team_root}")
    print(f"db:   {db_path}")
    print()


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    header_line = " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    separator_line = "-+-".join("-" * width for width in widths)
    print(header_line)
    print(separator_line)
    for row in rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def short_message_id(message_id: str) -> str:
    return message_id[-6:]


def format_timestamp_human(timestamp: str) -> str:
    try:
        normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return timestamp
    return parsed.strftime("%Y-%d-%m %H:%M:%S")


def show_task_detail(conn: sqlite3.Connection, task_id: str) -> None:
    row = conn.execute(
        """
        SELECT task_id, owner, state, body, priority, created_by, created_at, updated_at, blocked_reason
        FROM tasks
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchone()

    if row is None:
        print("Task not found.")
        return

    print()
    for key in (
        "task_id",
        "owner",
        "state",
        "priority",
        "created_by",
        "created_at",
        "updated_at",
        "blocked_reason",
    ):
        print(f"{key}: {row[key] or ''}")
    print("body:")
    print(row["body"])


def view_all_tasks(conn: sqlite3.Connection) -> None:
    clear_screen()
    print("View All Tasks")
    scope = prompt_scope("Task scope", TASK_SCOPE_CHOICES, "all")
    limit = prompt_int("Limit", 100)

    rows = runtime.query_task_rows(conn, owner=None, state_scope=scope, limit=limit)
    clear_screen()
    print(f"All tasks (scope={scope}, count={len(rows)})\n")

    if not rows:
        print("No tasks found.")
        pause()
        return

    table_rows = [
        [
            str(index),
            row["task_id"],
            row["owner"],
            row["state"],
            runtime.body_preview(row["body"], 48),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    print_table(["no", "task_id", "owner", "status", "body_preview"], table_rows)

    while rows:
        selected = prompt_numbered_selection("Task", len(rows))
        if selected is None:
            break
        show_task_detail(conn, rows[selected]["task_id"])

    pause()


def view_tasks_by_member(conn: sqlite3.Connection, team_root: Path) -> None:
    clear_screen()
    print("View Tasks By Member")
    member = prompt_member(conn, team_root)
    scope = prompt_scope("Task scope", TASK_SCOPE_CHOICES, "open")
    limit = prompt_int("Limit", 50)

    rows = runtime.query_task_rows(conn, owner=member, state_scope=scope, limit=limit)
    clear_screen()
    print(f"Tasks for {member} (scope={scope}, count={len(rows)})\n")
    print("no  task_id   state         prio updated_at            body")
    print("-" * 100)
    for index, row in enumerate(rows, start=1):
        print(
            f"{index:>2}  "
            f"{row['task_id'][:8]} "
            f"{row['state'][:12]:<12} "
            f"{str(row['priority']):>4} "
            f"{row['updated_at'][:20]:<20} "
            f"{runtime.body_preview(row['body'], 42)}"
        )

    while rows:
        selected = prompt_numbered_selection("Task", len(rows))
        if selected is None:
            break
        show_task_detail(conn, rows[selected]["task_id"])

    pause()


def read_message(conn: sqlite3.Connection, message_id: str) -> sqlite3.Row | None:
    result: dict[str, sqlite3.Row | None] = {"row": None}

    def _read(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            """
            SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
            FROM messages
            WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()
        if row is None:
            return

        if row["status"] == "unread":
            connection.execute(
                """
                UPDATE messages
                SET status = 'read', read_at = ?, archived_at = NULL
                WHERE message_id = ?
                """,
                (runtime.now_utc_iso(), message_id),
            )

        result["row"] = connection.execute(
            """
            SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
            FROM messages
            WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()

    runtime.with_write_transaction(conn, _read)
    return result["row"]


def archive_message_for_member(
    conn: sqlite3.Connection,
    member: str,
    message_id: str,
) -> sqlite3.Row | None:
    result: dict[str, sqlite3.Row | None] = {"row": None}

    def _archive(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            """
            SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
            FROM messages
            WHERE message_id = ? AND receiver = ?
            """,
            (message_id, member),
        ).fetchone()
        if row is None:
            return

        archived_at = runtime.now_utc_iso()
        read_at = row["read_at"] if row["read_at"] else archived_at
        connection.execute(
            """
            UPDATE messages
            SET status = 'archived', archived_at = ?, read_at = ?
            WHERE message_id = ? AND receiver = ?
            """,
            (archived_at, read_at, message_id, member),
        )

        result["row"] = connection.execute(
            """
            SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
            FROM messages
            WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()

    runtime.with_write_transaction(conn, _archive)
    return result["row"]


def print_message_detail(row: sqlite3.Row) -> None:
    print()
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
    ):
        print(f"{key}: {row[key] or ''}")
    print("body:")
    print(row["body"])


def send_ceo_message(
    conn: sqlite3.Connection,
    receiver: str,
    subject: str,
    body: str,
    task_id: str | None = None,
) -> str:
    message_id = str(uuid.uuid4())
    created_at = runtime.now_utc_iso()

    def _write(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO messages (
                message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
            ) VALUES (?, 'ceo', ?, ?, ?, ?, 'unread', NULL, NULL, ?)
            """,
            (message_id, receiver, subject, body, created_at, task_id),
        )

    runtime.with_write_transaction(conn, _write)
    return message_id


def unarchive_message_for_member(
    conn: sqlite3.Connection,
    member: str,
    message_id: str,
) -> sqlite3.Row | None:
    result: dict[str, sqlite3.Row | None] = {"row": None}

    def _unarchive(connection: sqlite3.Connection) -> None:
        existing = connection.execute(
            """
            SELECT message_id, status
            FROM messages
            WHERE message_id = ? AND receiver = ?
            """,
            (message_id, member),
        ).fetchone()
        if existing is None or existing["status"] != "archived":
            return

        connection.execute(
            """
            UPDATE messages
            SET status = 'read',
                read_at = COALESCE(read_at, ?),
                archived_at = NULL
            WHERE message_id = ? AND receiver = ?
            """,
            (runtime.now_utc_iso(), message_id, member),
        )

        updated = connection.execute(
            """
            SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
            FROM messages
            WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()
        result["row"] = updated

    runtime.with_write_transaction(conn, _unarchive)
    return result["row"]


def unarchive_messages_for_member(conn: sqlite3.Connection, team_root: Path) -> None:
    clear_screen()
    print("Unarchive Member Messages")
    member = prompt_member(conn, team_root)
    limit = prompt_int("Limit", 50)

    while True:
        rows = runtime.query_message_rows(
            conn=conn,
            member=member,
            status_scope="archived",
            sender=None,
            limit=limit,
        )

        clear_screen()
        print(f"Archived messages for {member} (count={len(rows)})\n")
        if not rows:
            print("No archived messages found.")
            pause()
            return

        table_rows = [
            [
                str(index),
                row["message_id"],
                row["receiver"],
                row["status"],
                runtime.body_preview(row["body"], 48),
            ]
            for index, row in enumerate(rows, start=1)
        ]
        print_table(["no", "message_id", "owner", "status", "body_preview"], table_rows)

        selected = prompt_numbered_selection("Archived message", len(rows))
        if selected is None:
            break

        message_id = rows[selected]["message_id"]
        updated = unarchive_message_for_member(conn, member, message_id)
        if updated is None:
            print("Message not found or not archived anymore.")
        else:
            print()
            print(f"unarchived: {updated['message_id']}")
            print(f"owner: {updated['receiver']}")
            print(f"status: {updated['status']}")

    pause()


def view_all_messages(conn: sqlite3.Connection) -> None:
    clear_screen()
    print("View All Messages")
    scope = prompt_scope("Message scope", MESSAGE_SCOPE_CHOICES, "all")
    limit = prompt_int("Limit", 100)

    clauses: list[str] = []
    params: list[object] = []
    if scope == "inbox":
        clauses.append("status IN ('unread', 'read')")
    elif scope != "all":
        clauses.append("status = ?")
        params.append(scope)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
        FROM messages
        {where_clause}
        ORDER BY receiver ASC, created_at DESC, message_id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()

    clear_screen()
    print(f"All messages (scope={scope}, count={len(rows)})\n")
    if not rows:
        print("No messages found.")
        pause()
        return

    table_rows = [
        [
            str(index),
            short_message_id(row["message_id"]),
            row["sender"],
            row["receiver"],
            format_timestamp_human(row["created_at"]),
            row["status"],
            runtime.body_preview(row["body"], 48),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    print_table(["no", "message_id", "from", "to", "timestamp", "status", "body_preview"], table_rows)

    while rows:
        selected = prompt_numbered_selection("Message", len(rows))
        if selected is None:
            break
        message = read_message(conn, rows[selected]["message_id"])
        if message is None:
            print("Message not found.")
            continue
        print_message_detail(message)
        if message["status"] != "archived" and prompt_yes_no("\nArchive this message?", default=False):
            updated = archive_message_for_member(conn, message["receiver"], message["message_id"])
            if updated is None:
                print("Message not found.")
            else:
                print(f"Message archived: {updated['message_id']}")
        elif message["status"] == "archived":
            print("\nMessage is already archived.")

    pause()


def view_messages(conn: sqlite3.Connection, team_root: Path, default_member: str | None = None) -> None:
    clear_screen()
    print("View Messages")
    member = prompt_member(conn, team_root, default=default_member)
    scope = prompt_scope("Message scope", MESSAGE_SCOPE_CHOICES, "inbox")
    sender_filter = prompt_line("Sender filter (blank for any)", "")
    sender: str | None = None
    if sender_filter:
        try:
            sender = runtime.normalize_identity(sender_filter, "sender")
        except ValueError as exc:
            print(exc)
            pause()
            return
    limit = prompt_int("Limit", 50)

    rows = runtime.query_message_rows(
        conn=conn,
        member=member,
        status_scope=scope,
        sender=sender,
        limit=limit,
    )

    clear_screen()
    print(f"Messages for {member} (scope={scope}, count={len(rows)})\n")
    table_rows = [
        [
            str(index),
            row["message_id"],
            row["receiver"],
            row["status"],
            runtime.body_preview(row["body"], 48),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    if table_rows:
        print_table(["no", "message_id", "owner", "status", "body_preview"], table_rows)
    else:
        print("No messages found.")

    while rows:
        selected = prompt_numbered_selection("Message", len(rows))
        if selected is None:
            break
        message = read_message(conn, rows[selected]["message_id"])
        if message is None:
            print("Message not found.")
            continue
        print_message_detail(message)
        if message["status"] != "archived" and prompt_yes_no("\nArchive this message?", default=False):
            updated = archive_message_for_member(conn, message["receiver"], message["message_id"])
            if updated is None:
                print("Message not found.")
            else:
                print(f"Message archived: {updated['message_id']}")
        elif message["status"] == "archived":
            print("\nMessage is already archived.")

    pause()


def respond_to_message(conn: sqlite3.Connection) -> None:
    clear_screen()
    print("Respond To Message")
    limit = prompt_int("Limit", 100)
    params: list[object] = ["ceo", limit]

    rows = conn.execute(
        """
        SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
        FROM messages
        WHERE receiver = ?
        ORDER BY receiver ASC, created_at DESC, message_id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()

    print("\nSelectable messages addressed to ceo (all statuses):")
    if not rows:
        print(" (none)")
        pause()
        return

    table_rows = [
        [
            str(index),
            short_message_id(row["message_id"]),
            row["sender"],
            row["receiver"],
            format_timestamp_human(row["created_at"]),
            row["status"],
            runtime.body_preview(row["body"], 48),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    print_table(["no", "message_id", "from", "to", "timestamp", "status", "body_preview"], table_rows)

    selected = prompt_numbered_selection("Message", len(rows))
    if selected is None:
        pause()
        return

    message_id = rows[selected]["message_id"]
    original = read_message(conn, message_id)
    if original is None:
        print("Message not found.")
        pause()
        return

    clear_screen()
    print("Original Message")
    print_message_detail(original)
    if original["status"] != "archived" and prompt_yes_no("\nArchive this message?", default=False):
        archived = archive_message_for_member(conn, original["receiver"], original["message_id"])
        if archived is None:
            print("Message not found.")
            pause()
            return
        original = archived
        print(f"Message archived: {original['message_id']}")
    elif original["status"] == "archived":
        print("\nMessage is already archived.")
    print()

    default_receiver = original["sender"]
    receiver_raw = prompt_line("Reply receiver", default_receiver)
    try:
        receiver = runtime.normalize_identity(receiver_raw, "receiver")
    except ValueError as exc:
        print(exc)
        pause()
        return

    subject_seed = original["subject"].strip() if original["subject"] else f"message {message_id[:8]}"
    subject = prompt_line("Reply subject", f"Re: {subject_seed}").strip()

    linked_task_raw = prompt_line("Linked task UUID (blank for none)", original["task_id"] or "")
    task_id: str | None
    if linked_task_raw:
        try:
            task_id = runtime.normalize_uuid(linked_task_raw, "task-id")
        except ValueError as exc:
            print(exc)
            pause()
            return
    else:
        task_id = None

    try:
        body = prompt_multiline("Reply body")
    except ValueError as exc:
        print(exc)
        pause()
        return

    reply_id = str(uuid.uuid4())
    created_at = runtime.now_utc_iso()
    read_at = runtime.now_utc_iso()

    def _write(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO messages (
                message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
            ) VALUES (?, 'ceo', ?, ?, ?, ?, 'unread', NULL, NULL, ?)
            """,
            (reply_id, receiver, subject, body, created_at, task_id),
        )

        connection.execute(
            """
            UPDATE messages
            SET status = CASE WHEN status = 'unread' THEN 'read' ELSE status END,
                read_at = CASE WHEN status = 'unread' AND read_at IS NULL THEN ? ELSE read_at END
            WHERE message_id = ?
            """,
            (read_at, message_id),
        )

    runtime.with_write_transaction(conn, _write)

    print("\nReply sent.")
    print(f"reply_id: {reply_id}")
    print(f"from: ceo")
    print(f"to: {receiver}")
    pause()


def send_message_to_member(conn: sqlite3.Connection, team_root: Path) -> None:
    clear_screen()
    print("Send Message To Member")

    receiver = prompt_member(conn, team_root)
    if receiver == "ceo":
        print("Receiver must be a team member (not 'ceo').")
        pause()
        return

    subject = prompt_line("Subject (blank for none)", "").strip()

    linked_task_raw = prompt_line("Linked task UUID (blank for none)", "")
    task_id: str | None
    if linked_task_raw:
        try:
            task_id = runtime.normalize_uuid(linked_task_raw, "task-id")
        except ValueError as exc:
            print(exc)
            pause()
            return
    else:
        task_id = None

    try:
        body = prompt_multiline("Message body")
    except ValueError as exc:
        print(exc)
        pause()
        return

    message_id = send_ceo_message(conn, receiver, subject, body, task_id)

    print("\nMessage sent.")
    print(f"message_id: {message_id}")
    print("from: ceo")
    print(f"to: {receiver}")
    pause()


def run_tui(conn: sqlite3.Connection, team_root: Path, db_path: Path) -> int:
    while True:
        clear_screen()
        print_header(team_root, db_path)
        print("1) View tasks by member")
        print("2) View all tasks")
        print("3) View messages for any member")
        print("4) View all messages")
        print("5) View CEO inbox")
        print("6) Respond to a message")
        print("7) Unarchive a member message")
        print("8) Send a message to a member")
        print("q) Quit")
        choice = input("\nSelect action: ").strip().lower()

        if choice == "1":
            view_tasks_by_member(conn, team_root)
        elif choice == "2":
            view_all_tasks(conn)
        elif choice == "3":
            view_messages(conn, team_root)
        elif choice == "4":
            view_all_messages(conn)
        elif choice == "5":
            view_messages(conn, team_root, default_member="ceo")
        elif choice == "6":
            respond_to_message(conn)
        elif choice == "7":
            unarchive_messages_for_member(conn, team_root)
        elif choice == "8":
            send_message_to_member(conn, team_root)
        elif choice in {"q", "quit", "exit"}:
            clear_screen()
            return 0
        else:
            print("Unknown option.")
            pause()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Human-only CEO terminal UI for team message/task oversight."
    )
    parser.add_argument(
        "--base",
        default=".",
        help="Base directory for resolving --team names/paths (default: current directory).",
    )
    parser.add_argument(
        "--team",
        required=True,
        help="Team name, TEAM_<name>, or path to a team directory.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        enforce_human_only_runtime()
    except PermissionError as exc:
        return fail(str(exc))

    base = Path(args.base).resolve()
    try:
        team_root = runtime.resolve_team_root(args.team, base)
        runtime.ensure_team_root(team_root)
    except ValueError as exc:
        return fail(str(exc))

    try:
        conn, db_path = runtime.ensure_database(team_root)
    except sqlite3.Error as exc:
        return fail(f"failed to initialize database: {exc}")

    try:
        return run_tui(conn, team_root, db_path)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
