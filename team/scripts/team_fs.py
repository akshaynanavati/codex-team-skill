#!/usr/bin/env python3
"""Filesystem helper for the team skill."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sqlite3
import sys
from pathlib import Path
from typing import Any

VALID_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
RUN_WRAPPER_FILENAME = "run"
RUN_WRAPPER_CUSTOM_MARKER = "# TEAM_RUN_WRAPPER_CUSTOM_CHECKS"
DB_FILENAME = "team_state.sqlite3"
TASK_STATES = ("todo", "in_progress", "blocked", "done", "cancelled")
MESSAGE_STATUSES = ("unread", "read", "archived")
MESSAGE_DIRECTIONS = ("inbound", "outbound")
OPTIMIZE_LARGE_FILE_BYTES = 8 * 1024
OPTIMIZE_LARGE_FILE_LINES = 200
TEXT_PREVIEW_WIDTH = 96


def fail(message: str) -> int:
    print(f"[ERROR] {message}", file=sys.stderr)
    return 1


def ensure_name(value: str, label: str) -> str:
    if "/" in value or "\\" in value:
        raise ValueError(f"{label} cannot contain path separators: {value!r}")
    if not VALID_NAME.match(value):
        raise ValueError(
            f"{label} must match {VALID_NAME.pattern} (letters, numbers, ., _, -)."
        )
    return value


def mission_template(mission: str) -> str:
    mission_text = mission.strip() or "TODO: define this team's mission."
    return f"# Mission\n{mission_text}\n"


def guidelines_template(guidelines: str) -> str:
    guidelines_text = (
        guidelines.strip()
        or "- TODO: define team-wide rules all members must follow."
    )
    return f"# Team Guidelines\n{guidelines_text}\n"


def role_template(role: str) -> str:
    role_text = role.strip() or "TODO: define this member's role and constraints."
    return f"# Role\n{role_text}\n"


def body_preview(text: str, width: int = TEXT_PREVIEW_WIDTH) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= width:
        return cleaned
    return f"{cleaned[: width - 3]}..."


def summarize_text_file(
    path: Path,
    *,
    ignored_values: set[str] | None = None,
) -> tuple[int, str]:
    line_count = 0
    summary = ""
    ignored = {value.strip().lower() for value in (ignored_values or set()) if value.strip()}

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line_count += 1
            stripped = raw_line.strip()
            if summary or not stripped:
                continue
            if stripped.startswith("#"):
                stripped = stripped.lstrip("#").strip()
            if stripped:
                if stripped.lower() in ignored:
                    continue
                summary = stripped

    return line_count, summary or "(empty)"


def ceo_wrapper_template(team_root: Path) -> str:
    team_root_quoted = shlex.quote(str(team_root))
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        'CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"\n'
        'TEAM_CEO_CLI="$CODEX_HOME/skills/team/scripts/team_ceo_cli.py"\n\n'
        f'exec python3 "$TEAM_CEO_CLI" "$@" --team {team_root_quoted}\n'
    )


def run_wrapper_template(team_root: Path) -> str:
    team_root_literal = repr(str(team_root.resolve()))
    return (
        "#!/usr/bin/env python3\n"
        '"""Team-local wrapper around the centralized team run scheduler."""\n\n'
        "from __future__ import annotations\n\n"
        "import importlib.util\n"
        "import os\n"
        "import sqlite3\n"
        "import subprocess\n"
        "import sys\n"
        "from pathlib import Path\n"
        "from typing import Callable\n\n"
        "CustomDecision = bool | None\n"
        "ShouldRunCheck = Callable[[sqlite3.Connection, str, Path], tuple[CustomDecision, str]]\n"
        f"TEAM_ROOT = Path({team_root_literal}).resolve()\n\n"
        "SPECIAL_MEMBER_CHECKS: dict[str, ShouldRunCheck] = {\n"
        "    # \"member-name\": should_run_member_name,\n"
        "}\n"
        f"{RUN_WRAPPER_CUSTOM_MARKER}\n\n"
        "def load_run_module(run_script: Path) -> object:\n"
        "    spec = importlib.util.spec_from_file_location(\"team_run_module\", run_script)\n"
        "    if spec is None or spec.loader is None:\n"
        "        raise RuntimeError(f\"unable to load run module from: {run_script}\")\n"
        "    module = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(module)\n"
        "    return module\n\n"
        "def resolve_run_script() -> Path:\n"
        "    codex_home = Path(os.environ.get(\"CODEX_HOME\", str(Path.home() / \".codex\")))\n"
        "    return (codex_home / \"skills\" / \"team\" / \"scripts\" / \"run.py\").resolve()\n\n"
        "def main() -> int:\n"
        "    if not TEAM_ROOT.exists() or not TEAM_ROOT.is_dir():\n"
        "        print(f\"[ERROR] team directory not found: {TEAM_ROOT}\", file=sys.stderr)\n"
        "        return 1\n\n"
        "    forwarded_args = list(sys.argv[1:])\n"
        "    help_requested = any(arg in {\"-h\", \"--help\"} for arg in forwarded_args)\n"
        "    run_script = resolve_run_script()\n"
        "    if not run_script.exists() or not run_script.is_file():\n"
        "        print(f\"[ERROR] team run script not found: {run_script}\", file=sys.stderr)\n"
        "        return 1\n\n"
        "    allow_members: set[str] = set()\n"
        "    deny_members: set[str] = set()\n"
        "    if not help_requested and SPECIAL_MEMBER_CHECKS:\n"
        "        try:\n"
        "            run_module = load_run_module(run_script)\n"
        "            collect_filters = getattr(run_module, \"collect_custom_member_filters\")\n"
        "            allow_members, deny_members = collect_filters(TEAM_ROOT, SPECIAL_MEMBER_CHECKS)\n"
        "        except (AttributeError, FileNotFoundError, RuntimeError, TypeError, sqlite3.Error, ValueError) as exc:\n"
        "            print(f\"[ERROR] unable to evaluate custom run checks: {exc}\", file=sys.stderr)\n"
        "            return 1\n\n"
        "    command: list[str] = [\"python3\", str(run_script)]\n"
        "    command.extend(forwarded_args)\n"
        "    for member in sorted(allow_members):\n"
        "        command.extend([\"--allow-member\", member])\n"
        "    for member in sorted(deny_members):\n"
        "        command.extend([\"--deny-member\", member])\n"
        "    command.extend([\"--team\", str(TEAM_ROOT)])\n\n"
        "    try:\n"
        "        return subprocess.run(command, check=False).returncode\n"
        "    except OSError as exc:\n"
        "        print(f\"[ERROR] unable to launch team run script: {exc}\", file=sys.stderr)\n"
        "        return 1\n\n"
        "if __name__ == \"__main__\":\n"
        "    raise SystemExit(main())\n"
    )


def write_team_run_wrapper(team_root: Path, overwrite: bool) -> None:
    run_path = team_root / RUN_WRAPPER_FILENAME
    if run_path.exists() and run_path.is_dir():
        raise ValueError(f"run wrapper target exists as a directory: {run_path}")
    if run_path.exists() and not overwrite:
        print(f"[SKIP] run wrapper exists: {run_path}")
        return

    run_path.write_text(run_wrapper_template(team_root), encoding="utf-8")
    run_path.chmod(0o755)
    print(f"[OK] wrote run wrapper: {run_path}")


def member_identity(member_name: str) -> str:
    return ensure_name(member_name, "member name").lower()


def member_function_token(member: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", member.lower()).strip("_")
    if not token:
        return "member_custom"
    if token[0].isdigit():
        return f"member_{token}"
    return token


def build_custom_run_check_snippet(member: str, criteria: str) -> str:
    member_id = member_identity(member)
    fn_token = member_function_token(member_id)

    criteria_lines = [line.strip() for line in criteria.splitlines() if line.strip()]
    if not criteria_lines:
        criteria_lines = ["TODO: fill in run criteria details."]
    criteria_comment = "\n".join(f"    # - {line}" for line in criteria_lines)

    return (
        "\n"
        f"def should_run_{fn_token}(\n"
        "    conn: sqlite3.Connection,\n"
        "    member: str,\n"
        "    team_root: Path,\n"
        ") -> tuple[bool | None, str]:\n"
        f"    \"\"\"Custom run rule for '{member_id}'.\"\"\"\n"
        "    # Recruit-time criteria:\n"
        f"{criteria_comment}\n"
        "    # Return True to force a run, False to skip, or None to defer.\n"
        "    # TODO: replace fallback with this member's specific run criteria.\n"
        "    return None, \"TODO custom run criteria not implemented; defer to run.py defaults\"\n"
        "\n"
        f"SPECIAL_MEMBER_CHECKS[\"{member_id}\"] = should_run_{fn_token}\n"
        "\n"
    )


def ensure_member_custom_run_check(team_root: Path, member: str, criteria: str) -> None:
    run_path = team_root / RUN_WRAPPER_FILENAME
    if not run_path.exists():
        write_team_run_wrapper(team_root, overwrite=False)
    if not run_path.exists() or not run_path.is_file():
        raise FileNotFoundError(f"team run wrapper not found: {run_path}")

    member_id = member_identity(member)
    registration = f'SPECIAL_MEMBER_CHECKS["{member_id}"] = '

    source = run_path.read_text(encoding="utf-8")
    if registration in source:
        print(f"[SKIP] custom run check already exists for member '{member_id}': {run_path}")
        return
    if RUN_WRAPPER_CUSTOM_MARKER not in source:
        raise ValueError(
            f"run wrapper is missing expected marker '{RUN_WRAPPER_CUSTOM_MARKER}': {run_path}"
        )

    snippet = build_custom_run_check_snippet(member_id, criteria)
    updated = source.replace(
        RUN_WRAPPER_CUSTOM_MARKER, f"{snippet}{RUN_WRAPPER_CUSTOM_MARKER}", 1
    )
    run_path.write_text(updated, encoding="utf-8")
    print(f"[OK] added custom run check for member '{member_id}' in run wrapper: {run_path}")


def resolve_member_dir(team_root: Path, member: str) -> Path:
    members_dir = team_root / "members"
    if not members_dir.exists() or not members_dir.is_dir():
        raise FileNotFoundError(f"members directory not found: {members_dir}")

    member_id = member_identity(member)
    matches: list[Path] = []
    for child in sorted(members_dir.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        try:
            child_id = member_identity(child.name)
        except ValueError:
            continue
        if child_id == member_id:
            matches.append(child.resolve())

    if not matches:
        raise FileNotFoundError(f"member directory not found: {members_dir / member}")
    if len(matches) > 1:
        joined = ", ".join(str(path) for path in matches)
        raise ValueError(f"multiple member directories resolve to '{member_id}': {joined}")
    return matches[0]


def connect_runtime_db(team_root: Path) -> tuple[sqlite3.Connection | None, Path]:
    db_path = team_root / "state" / DB_FILENAME
    if not db_path.exists():
        return None, db_path

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn, db_path


def collect_context_files(context_dir: Path, team_root: Path) -> list[dict[str, Any]]:
    if not context_dir.exists() or not context_dir.is_dir():
        return []

    records: list[dict[str, Any]] = []
    for path in sorted(context_dir.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        line_count, summary = summarize_text_file(path)
        records.append(
            {
                "path": str(path.relative_to(team_root)),
                "bytes": stat.st_size,
                "lines": line_count,
                "summary": body_preview(summary),
                "needs_split": (
                    stat.st_size >= OPTIMIZE_LARGE_FILE_BYTES
                    or line_count >= OPTIMIZE_LARGE_FILE_LINES
                ),
            }
        )

    records.sort(key=lambda record: (-int(record["bytes"]), str(record["path"])))
    return records


def query_task_counts(conn: sqlite3.Connection, owner: str) -> dict[str, int]:
    counts = {state: 0 for state in TASK_STATES}
    rows = conn.execute(
        """
        SELECT state, COUNT(*) AS c
        FROM tasks
        WHERE owner = ?
        GROUP BY state
        """,
        (owner,),
    ).fetchall()
    for row in rows:
        counts[str(row["state"])] = int(row["c"])
    return counts


def query_recent_tasks(
    conn: sqlite3.Connection,
    owner: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT task_id, state, priority, created_at, updated_at, blocked_reason, body
        FROM tasks
        WHERE owner = ?
        ORDER BY
            CASE state
                WHEN 'in_progress' THEN 0
                WHEN 'todo' THEN 1
                WHEN 'blocked' THEN 2
                WHEN 'done' THEN 3
                WHEN 'cancelled' THEN 4
                ELSE 5
            END,
            updated_at DESC,
            created_at DESC,
            task_id ASC
        LIMIT ?
        """,
        (owner, limit),
    ).fetchall()
    return [
        {
            "task_id": str(row["task_id"]),
            "state": str(row["state"]),
            "priority": int(row["priority"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "blocked_reason": str(row["blocked_reason"] or ""),
            "body_preview": body_preview(str(row["body"] or "")),
        }
        for row in rows
    ]


def query_message_counts(conn: sqlite3.Connection, member: str) -> dict[str, int]:
    counts = {status: 0 for status in MESSAGE_STATUSES}
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM messages
        WHERE receiver = ?
        GROUP BY status
        """,
        (member,),
    ).fetchall()
    for row in rows:
        counts[str(row["status"])] = int(row["c"])
    return counts


def query_recent_messages(
    conn: sqlite3.Connection,
    member: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT message_id, sender, subject, body, created_at, status, task_id
        FROM messages
        WHERE receiver = ?
        ORDER BY
            CASE status
                WHEN 'unread' THEN 0
                WHEN 'read' THEN 1
                WHEN 'archived' THEN 2
                ELSE 3
            END,
            created_at DESC,
            message_id ASC
        LIMIT ?
        """,
        (member, limit),
    ).fetchall()
    return [
        {
            "message_id": str(row["message_id"]),
            "status": str(row["status"]),
            "sender": str(row["sender"]),
            "created_at": str(row["created_at"]),
            "subject": str(row["subject"] or ""),
            "task_id": str(row["task_id"] or ""),
            "body_preview": body_preview(str(row["body"] or "")),
        }
        for row in rows
    ]


def query_training_task_summary(conn: sqlite3.Connection, owner: str) -> dict[str, Any]:
    counts = query_task_counts(conn, owner)
    rows = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN state = 'done' THEN 1 ELSE 0 END), 0) AS done_total,
            COALESCE(SUM(CASE WHEN state = 'blocked' THEN 1 ELSE 0 END), 0) AS blocked_total,
            COALESCE(MAX(updated_at), '') AS last_updated_at
        FROM tasks
        WHERE owner = ?
        """,
        (owner,),
    ).fetchone()
    assert rows is not None
    return {
        "counts": counts,
        "total": int(rows["total"]),
        "done_total": int(rows["done_total"]),
        "blocked_total": int(rows["blocked_total"]),
        "last_updated_at": str(rows["last_updated_at"] or ""),
    }


def query_cross_member_message_counts(conn: sqlite3.Connection, member: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT
            SUM(CASE WHEN receiver = ? THEN 1 ELSE 0 END) AS inbound_total,
            SUM(CASE WHEN sender = ? THEN 1 ELSE 0 END) AS outbound_total,
            COUNT(*) AS total
        FROM messages
        WHERE (sender = ? OR receiver = ?)
          AND sender != receiver
        """,
        (member, member, member, member),
    ).fetchone()
    assert rows is not None
    return {
        "inbound": int(rows["inbound_total"] or 0),
        "outbound": int(rows["outbound_total"] or 0),
        "total": int(rows["total"] or 0),
    }


def query_training_correspondents(
    conn: sqlite3.Connection,
    member: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            CASE
                WHEN sender = ? THEN receiver
                ELSE sender
            END AS counterpart,
            COUNT(*) AS exchange_count,
            COALESCE(SUM(CASE WHEN receiver = ? THEN 1 ELSE 0 END), 0) AS inbound_count,
            COALESCE(SUM(CASE WHEN sender = ? THEN 1 ELSE 0 END), 0) AS outbound_count,
            COALESCE(MAX(created_at), '') AS last_contact_at
        FROM messages
        WHERE (sender = ? OR receiver = ?)
          AND sender != receiver
        GROUP BY counterpart
        ORDER BY exchange_count DESC, last_contact_at DESC, counterpart ASC
        LIMIT ?
        """,
        (member, member, member, member, member, limit),
    ).fetchall()
    return [
        {
            "counterpart": str(row["counterpart"]),
            "exchange_count": int(row["exchange_count"]),
            "inbound_count": int(row["inbound_count"]),
            "outbound_count": int(row["outbound_count"]),
            "last_contact_at": str(row["last_contact_at"] or ""),
        }
        for row in rows
    ]


def query_training_messages(
    conn: sqlite3.Connection,
    member: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            message_id,
            sender,
            receiver,
            subject,
            body,
            created_at,
            status,
            task_id
        FROM messages
        WHERE (sender = ? OR receiver = ?)
          AND sender != receiver
        ORDER BY created_at DESC, message_id ASC
        LIMIT ?
        """,
        (member, member, limit),
    ).fetchall()
    return [
        {
            "message_id": str(row["message_id"]),
            "direction": "inbound" if str(row["receiver"]) == member else "outbound",
            "counterpart": (
                str(row["sender"]) if str(row["receiver"]) == member else str(row["receiver"])
            ),
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
            "subject": str(row["subject"] or ""),
            "task_id": str(row["task_id"] or ""),
            "body_preview": body_preview(str(row["body"] or "")),
        }
        for row in rows
    ]


def build_optimize_report(
    team_root: Path,
    member_dir: Path,
    member: str,
    *,
    task_limit: int,
    message_limit: int,
) -> dict[str, Any]:
    role_path = member_dir / "ROLE.md"
    if not role_path.exists() or not role_path.is_file():
        raise FileNotFoundError(f"member role not found: {role_path}")

    role_lines, role_summary = summarize_text_file(role_path, ignored_values={"Role"})
    context_dir = member_dir / "context"
    context_files = collect_context_files(context_dir, team_root)

    report: dict[str, Any] = {
        "team_root": str(team_root),
        "member": member,
        "member_dir": str(member_dir),
        "role": {
            "path": str(role_path),
            "lines": role_lines,
            "summary": body_preview(role_summary),
        },
        "context": {
            "path": str(context_dir),
            "exists": context_dir.exists() and context_dir.is_dir(),
            "file_count": len(context_files),
            "total_bytes": sum(int(record["bytes"]) for record in context_files),
            "total_lines": sum(int(record["lines"]) for record in context_files),
            "oversized_threshold_bytes": OPTIMIZE_LARGE_FILE_BYTES,
            "oversized_threshold_lines": OPTIMIZE_LARGE_FILE_LINES,
            "oversized_files": [
                record["path"] for record in context_files if bool(record["needs_split"])
            ],
            "files": context_files,
        },
        "runtime": {
            "db_path": "",
            "available": False,
            "tasks": None,
            "messages": None,
        },
    }

    conn, db_path = connect_runtime_db(team_root)
    report["runtime"]["db_path"] = str(db_path)
    if conn is None:
        return report

    try:
        report["runtime"]["available"] = True
        report["runtime"]["tasks"] = {
            "counts": query_task_counts(conn, member),
            "recent": query_recent_tasks(conn, member, task_limit),
        }
        report["runtime"]["messages"] = {
            "counts": query_message_counts(conn, member),
            "recent": query_recent_messages(conn, member, message_limit),
        }
        return report
    finally:
        conn.close()


def print_optimize_report(report: dict[str, Any]) -> None:
    print(f"team_root: {report['team_root']}")
    print(f"member: {report['member']}")
    print(f"member_dir: {report['member_dir']}")

    role = report["role"]
    print(f"role_path: {role['path']}")
    print(f"role_lines: {role['lines']}")
    print(f"role_summary: {role['summary']}")

    context = report["context"]
    print(f"context_path: {context['path']}")
    print(f"context_exists: {context['exists']}")
    print(f"context_file_count: {context['file_count']}")
    print(f"context_total_bytes: {context['total_bytes']}")
    print(f"context_total_lines: {context['total_lines']}")
    print(
        "context_oversized_thresholds: "
        f"{context['oversized_threshold_bytes']} bytes or "
        f"{context['oversized_threshold_lines']} lines"
    )
    print("context_files:")
    files = context["files"]
    if not files:
        print("  (none)")
    for record in files:
        marker = " split" if record["needs_split"] else ""
        print(
            f"  - {record['path']} | {record['bytes']} bytes | "
            f"{record['lines']} lines{marker}"
        )
        print(f"    summary: {record['summary']}")

    runtime = report["runtime"]
    print(f"runtime_db_path: {runtime['db_path']}")
    print(f"runtime_available: {runtime['available']}")
    if not runtime["available"]:
        return

    tasks = runtime["tasks"]
    assert tasks is not None
    task_counts = tasks["counts"]
    print(
        "task_counts: "
        + ", ".join(f"{state}={task_counts[state]}" for state in TASK_STATES)
    )
    print("recent_tasks:")
    if not tasks["recent"]:
        print("  (none)")
    for record in tasks["recent"]:
        suffix = ""
        if record["blocked_reason"]:
            suffix = f" | blocked_reason={record['blocked_reason']}"
        print(
            f"  - {record['task_id']} [{record['state']}] "
            f"priority={record['priority']} updated_at={record['updated_at']}{suffix}"
        )
        print(f"    body: {record['body_preview']}")

    messages = runtime["messages"]
    assert messages is not None
    message_counts = messages["counts"]
    print(
        "message_counts: "
        + ", ".join(f"{status}={message_counts[status]}" for status in MESSAGE_STATUSES)
    )
    print("recent_messages:")
    if not messages["recent"]:
        print("  (none)")
    for record in messages["recent"]:
        task_suffix = f" task={record['task_id']}" if record["task_id"] else ""
        subject = record["subject"] or "(no subject)"
        print(
            f"  - {record['message_id']} [{record['status']}] "
            f"from={record['sender']} created_at={record['created_at']}{task_suffix}"
        )
        print(f"    subject: {body_preview(subject)}")
        print(f"    body: {record['body_preview']}")


def build_train_report(
    team_root: Path,
    member_dir: Path,
    member: str,
    *,
    task_limit: int,
    message_limit: int,
    correspondent_limit: int,
) -> dict[str, Any]:
    role_path = member_dir / "ROLE.md"
    if not role_path.exists() or not role_path.is_file():
        raise FileNotFoundError(f"member role not found: {role_path}")

    role_text = role_path.read_text(encoding="utf-8")
    role_lines, role_summary = summarize_text_file(role_path, ignored_values={"Role"})

    report: dict[str, Any] = {
        "team_root": str(team_root),
        "member": member,
        "member_dir": str(member_dir),
        "role": {
            "path": str(role_path),
            "lines": role_lines,
            "summary": body_preview(role_summary),
            "body": role_text,
        },
        "runtime": {
            "db_path": "",
            "available": False,
            "tasks": None,
            "messages": None,
        },
    }

    conn, db_path = connect_runtime_db(team_root)
    report["runtime"]["db_path"] = str(db_path)
    if conn is None:
        return report

    try:
        report["runtime"]["available"] = True
        report["runtime"]["tasks"] = {
            "summary": query_training_task_summary(conn, member),
            "recent": query_recent_tasks(conn, member, task_limit),
        }
        report["runtime"]["messages"] = {
            "summary": query_cross_member_message_counts(conn, member),
            "correspondents": query_training_correspondents(conn, member, correspondent_limit),
            "recent": query_training_messages(conn, member, message_limit),
        }
        return report
    finally:
        conn.close()


def print_train_report(report: dict[str, Any]) -> None:
    print(f"team_root: {report['team_root']}")
    print(f"member: {report['member']}")
    print(f"member_dir: {report['member_dir']}")

    role = report["role"]
    print(f"role_path: {role['path']}")
    print(f"role_lines: {role['lines']}")
    print(f"role_summary: {role['summary']}")
    print("role_body:")
    for line in str(role["body"]).splitlines():
        print(f"  {line}")

    runtime = report["runtime"]
    print(f"runtime_db_path: {runtime['db_path']}")
    print(f"runtime_available: {runtime['available']}")
    if not runtime["available"]:
        return

    tasks = runtime["tasks"]
    assert tasks is not None
    task_summary = tasks["summary"]
    task_counts = task_summary["counts"]
    print(
        "task_counts: "
        + ", ".join(f"{state}={task_counts[state]}" for state in TASK_STATES)
    )
    print(f"task_total: {task_summary['total']}")
    print(f"task_done_total: {task_summary['done_total']}")
    print(f"task_blocked_total: {task_summary['blocked_total']}")
    print(f"task_last_updated_at: {task_summary['last_updated_at']}")
    print("recent_tasks:")
    if not tasks["recent"]:
        print("  (none)")
    for record in tasks["recent"]:
        suffix = ""
        if record["blocked_reason"]:
            suffix = f" | blocked_reason={record['blocked_reason']}"
        print(
            f"  - {record['task_id']} [{record['state']}] "
            f"priority={record['priority']} updated_at={record['updated_at']}{suffix}"
        )
        print(f"    body: {record['body_preview']}")

    messages = runtime["messages"]
    assert messages is not None
    message_summary = messages["summary"]
    print(
        "message_totals: "
        + ", ".join(f"{direction}={message_summary[direction]}" for direction in MESSAGE_DIRECTIONS)
        + f", total={message_summary['total']}"
    )
    print("top_correspondents:")
    if not messages["correspondents"]:
        print("  (none)")
    for record in messages["correspondents"]:
        print(
            f"  - {record['counterpart']} | exchanges={record['exchange_count']} "
            f"| inbound={record['inbound_count']} | outbound={record['outbound_count']} "
            f"| last_contact_at={record['last_contact_at']}"
        )
    print("recent_cross_member_messages:")
    if not messages["recent"]:
        print("  (none)")
    for record in messages["recent"]:
        task_suffix = f" task={record['task_id']}" if record["task_id"] else ""
        subject = record["subject"] or "(no subject)"
        print(
            f"  - {record['message_id']} [{record['direction']}] "
            f"counterpart={record['counterpart']} created_at={record['created_at']}{task_suffix}"
        )
        print(f"    subject: {body_preview(subject)}")
        print(f"    body: {record['body_preview']}")


def resolve_team_root(team: str, base: Path) -> Path:
    team_path = Path(team)

    if team_path.is_absolute():
        return team_path.resolve()

    if len(team_path.parts) > 1 or team.startswith("."):
        return (base / team_path).resolve()

    if team.startswith("TEAM_"):
        team_name = team[len("TEAM_") :]
        if not team_name:
            raise ValueError("team value 'TEAM_' is invalid.")
        ensure_name(team_name, "team name")
        return (base / team).resolve()

    ensure_name(team, "team name")
    return (base / f"TEAM_{team}").resolve()


def cmd_create(args: argparse.Namespace) -> int:
    try:
        team_name = ensure_name(args.name, "team name")
    except ValueError as exc:
        return fail(str(exc))

    base = Path(args.base).resolve()
    team_root = (base / f"TEAM_{team_name}").resolve()

    if team_root.exists() and not team_root.is_dir():
        return fail(f"target exists but is not a directory: {team_root}")

    team_root.mkdir(parents=True, exist_ok=True)
    (team_root / "members").mkdir(exist_ok=True)
    (team_root / "state").mkdir(exist_ok=True)

    mission_path = team_root / "mission.md"
    if mission_path.exists() and not args.overwrite_mission:
        print(f"[SKIP] mission exists: {mission_path}")
    else:
        mission_path.write_text(mission_template(args.mission), encoding="utf-8")
        print(f"[OK] wrote mission: {mission_path}")

    guidelines_path = team_root / "guidelines.md"
    if guidelines_path.exists() and not args.overwrite_guidelines:
        print(f"[SKIP] guidelines exist: {guidelines_path}")
    else:
        guidelines_path.write_text(guidelines_template(args.guidelines), encoding="utf-8")
        print(f"[OK] wrote guidelines: {guidelines_path}")

    ceo_wrapper_path = team_root / "ceo"
    if ceo_wrapper_path.exists() and ceo_wrapper_path.is_dir():
        return fail(f"ceo wrapper target exists as a directory: {ceo_wrapper_path}")
    if ceo_wrapper_path.exists() and not args.overwrite_ceo_wrapper:
        print(f"[SKIP] ceo wrapper exists: {ceo_wrapper_path}")
    else:
        ceo_wrapper_path.write_text(ceo_wrapper_template(team_root), encoding="utf-8")
        ceo_wrapper_path.chmod(0o755)
        print(f"[OK] wrote ceo wrapper: {ceo_wrapper_path}")

    try:
        write_team_run_wrapper(team_root, overwrite=args.overwrite_run_wrapper)
    except (FileNotFoundError, OSError, ValueError) as exc:
        return fail(str(exc))

    print(f"[OK] team ready: {team_root}")
    return 0


def cmd_recruit(args: argparse.Namespace) -> int:
    try:
        member_name = ensure_name(args.name, "member name")
    except ValueError as exc:
        return fail(str(exc))

    base = Path(args.base).resolve()
    try:
        team_root = resolve_team_root(args.team, base)
    except ValueError as exc:
        return fail(str(exc))

    if not team_root.exists() or not team_root.is_dir():
        return fail(f"team directory not found: {team_root}")

    members_dir = team_root / "members"
    members_dir.mkdir(exist_ok=True)

    member_dir = members_dir / member_name
    member_dir.mkdir(parents=True, exist_ok=True)
    (member_dir / "context").mkdir(exist_ok=True)

    role_path = member_dir / "ROLE.md"
    if role_path.exists() and not args.overwrite_role:
        print(f"[SKIP] role exists: {role_path}")
    else:
        role_path.write_text(role_template(args.role), encoding="utf-8")
        print(f"[OK] wrote role: {role_path}")

    run_check = args.run_check.strip()
    if run_check:
        try:
            ensure_member_custom_run_check(team_root, member_name, run_check)
        except (FileNotFoundError, OSError, ValueError) as exc:
            return fail(str(exc))

    print(f"[OK] member ready: {member_dir}")
    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    if args.task_limit <= 0:
        return fail("--task-limit must be greater than 0.")
    if args.message_limit <= 0:
        return fail("--message-limit must be greater than 0.")

    base = Path(args.base).resolve()
    try:
        team_root = resolve_team_root(args.team, base)
        member_dir = resolve_member_dir(team_root, args.name)
        member_name = member_identity(member_dir.name)
        report = build_optimize_report(
            team_root,
            member_dir,
            member_name,
            task_limit=args.task_limit,
            message_limit=args.message_limit,
        )
    except (FileNotFoundError, OSError, ValueError, sqlite3.Error) as exc:
        return fail(str(exc))

    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print_optimize_report(report)
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    if args.task_limit <= 0:
        return fail("--task-limit must be greater than 0.")
    if args.message_limit <= 0:
        return fail("--message-limit must be greater than 0.")
    if args.correspondent_limit <= 0:
        return fail("--correspondent-limit must be greater than 0.")

    base = Path(args.base).resolve()
    try:
        team_root = resolve_team_root(args.team, base)
        member_dir = resolve_member_dir(team_root, args.name)
        member_name = member_identity(member_dir.name)
        report = build_train_report(
            team_root,
            member_dir,
            member_name,
            task_limit=args.task_limit,
            message_limit=args.message_limit,
            correspondent_limit=args.correspondent_limit,
        )
    except (FileNotFoundError, OSError, ValueError, sqlite3.Error) as exc:
        return fail(str(exc))

    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print_train_report(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create teams, recruit members, and inspect member state for optimization or training."
    )
    parser.add_argument(
        "--base",
        default=".",
        help="Base directory for relative paths (default: current directory).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create TEAM_<name> structure.")
    create_parser.add_argument("--name", required=True, help="Team name, without TEAM_ prefix.")
    create_parser.add_argument(
        "--mission",
        default="",
        help="Mission text for mission.md. Empty writes a TODO placeholder.",
    )
    create_parser.add_argument(
        "--overwrite-mission",
        action="store_true",
        help="Overwrite mission.md if it already exists.",
    )
    create_parser.add_argument(
        "--guidelines",
        default="",
        help="Team-wide rules for guidelines.md. Empty writes a TODO placeholder.",
    )
    create_parser.add_argument(
        "--overwrite-guidelines",
        action="store_true",
        help="Overwrite guidelines.md if it already exists.",
    )
    create_parser.add_argument(
        "--overwrite-ceo-wrapper",
        action="store_true",
        help="Overwrite TEAM_<name>/ceo if it already exists.",
    )
    create_parser.add_argument(
        "--overwrite-run-wrapper",
        dest="overwrite_run_wrapper",
        action="store_true",
        help="Overwrite TEAM_<name>/run if it already exists.",
    )
    create_parser.add_argument(
        "--overwrite-runner",
        dest="overwrite_run_wrapper",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    create_parser.set_defaults(func=cmd_create)

    recruit_parser = subparsers.add_parser("recruit", help="Create member scaffolding.")
    recruit_parser.add_argument(
        "--team",
        required=True,
        help="Team name or team path. Name resolves to TEAM_<name> under --base.",
    )
    recruit_parser.add_argument("--name", required=True, help="Member name.")
    recruit_parser.add_argument(
        "--role",
        default="",
        help="Role text for ROLE.md. Empty writes a TODO placeholder.",
    )
    recruit_parser.add_argument(
        "--overwrite-role",
        action="store_true",
        help="Overwrite ROLE.md if it already exists.",
    )
    recruit_parser.add_argument(
        "--run-check",
        default="",
        help=(
            "Optional member-specific run criteria text. When provided, "
            "TEAM_<name>/run is updated with a custom check stub for this member."
        ),
    )
    recruit_parser.set_defaults(func=cmd_recruit)

    optimize_parser = subparsers.add_parser(
        "optimize",
        help="Inspect one member's role, context, tasks, and messages for context cleanup.",
    )
    optimize_parser.add_argument(
        "--team",
        required=True,
        help="Team name or team path. Name resolves to TEAM_<name> under --base.",
    )
    optimize_parser.add_argument("--name", required=True, help="Member name.")
    optimize_parser.add_argument(
        "--task-limit",
        type=int,
        default=15,
        help="Maximum recent tasks to include (default: 15).",
    )
    optimize_parser.add_argument(
        "--message-limit",
        type=int,
        default=15,
        help="Maximum recent messages to include (default: 15).",
    )
    optimize_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON for the optimize snapshot.",
    )
    optimize_parser.set_defaults(func=cmd_optimize)

    train_parser = subparsers.add_parser(
        "train",
        help="Inspect one member's role, tasks, and cross-member messages for role refinement.",
    )
    train_parser.add_argument(
        "--team",
        required=True,
        help="Team name or team path. Name resolves to TEAM_<name> under --base.",
    )
    train_parser.add_argument("--name", required=True, help="Member name.")
    train_parser.add_argument(
        "--task-limit",
        type=int,
        default=20,
        help="Maximum recent tasks to include (default: 20).",
    )
    train_parser.add_argument(
        "--message-limit",
        type=int,
        default=25,
        help="Maximum recent cross-member messages to include (default: 25).",
    )
    train_parser.add_argument(
        "--correspondent-limit",
        type=int,
        default=10,
        help="Maximum correspondents to summarize (default: 10).",
    )
    train_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON for the training snapshot.",
    )
    train_parser.set_defaults(func=cmd_train)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
