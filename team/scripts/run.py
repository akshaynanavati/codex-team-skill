#!/usr/bin/env python3
"""Run team members that currently need a work round.

This file is copied to TEAM_<name>/run.py during team creation and is designed
to be customized per team.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Callable

VALID_MEMBER = re.compile(r"^[A-Za-z0-9._-]+$")
DB_FILENAME = "team_state.sqlite3"
REASONING_LEVELS = ("low", "medium", "high", "xhigh")
CEO_UNREAD_PREVIEW_LIMIT = 10
MESSAGE_BODY_PREVIEW_WIDTH = 96

ShouldRunCheck = Callable[[sqlite3.Connection, str, Path], tuple[bool, str]]


def fail(message: str) -> int:
    print(f"[ERROR] {message}", file=sys.stderr)
    return 1


def normalize_member(value: str, label: str = "member") -> str:
    member = value.strip()
    if not member:
        raise ValueError(f"{label} cannot be empty.")
    if "/" in member or "\\" in member:
        raise ValueError(f"{label} cannot contain path separators: {value!r}")
    if not VALID_MEMBER.match(member):
        raise ValueError(
            f"{label} must match {VALID_MEMBER.pattern} (letters, numbers, ., _, -)."
        )
    return member.lower()


def resolve_team_root(raw: str | None, default_root: Path) -> Path:
    if raw is None or not raw.strip():
        return default_root.resolve()

    team_input = raw.strip()
    team_path = Path(team_input)

    if team_path.is_absolute():
        return team_path.resolve()

    if len(team_path.parts) > 1 or team_input.startswith("."):
        return (Path.cwd() / team_path).resolve()

    if team_input.startswith("TEAM_"):
        return (Path.cwd() / team_input).resolve()

    return (Path.cwd() / f"TEAM_{team_input}").resolve()


def discover_members(team_root: Path) -> dict[str, str]:
    members_dir = team_root / "members"
    if not members_dir.is_dir():
        return {}

    members: dict[str, str] = {}
    for child in sorted(members_dir.iterdir(), key=lambda path: path.name.lower()):
        if not child.is_dir():
            continue
        try:
            member_key = normalize_member(child.name)
        except ValueError:
            continue

        previous = members.get(member_key)
        if previous and previous != child.name:
            print(
                f"[WARN] duplicate member identity '{member_key}' from '{previous}' "
                f"and '{child.name}'. Keeping '{previous}'.",
                file=sys.stderr,
            )
            continue
        members[member_key] = child.name

    return dict(sorted(members.items()))


def connect_database(team_root: Path) -> sqlite3.Connection:
    db_path = team_root / "state" / DB_FILENAME
    if not db_path.exists():
        raise FileNotFoundError(f"team state database not found: {db_path}")

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def count_unread_messages(conn: sqlite3.Connection, member: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM messages
        WHERE receiver = ? AND status = 'unread'
        """,
        (member,),
    ).fetchone()
    return int(row["c"]) if row is not None else 0


def preview_text(text: str, width: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= width:
        return cleaned
    if width <= 3:
        return cleaned[:width]
    return f"{cleaned[: width - 3]}..."


def list_unread_messages(
    conn: sqlite3.Connection,
    member: str,
    *,
    limit: int,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT message_id, sender, subject, body, created_at, task_id
        FROM messages
        WHERE receiver = ? AND status = 'unread'
        ORDER BY created_at DESC, message_id ASC
        LIMIT ?
        """,
        (member, limit),
    ).fetchall()
    return list(rows)


def print_unread_message_preview(
    unread_count: int,
    rows: list[sqlite3.Row],
) -> None:
    print("        Unread CEO messages:")
    for row in rows:
        message_id = str(row["message_id"])
        sender = str(row["sender"])
        created_at = str(row["created_at"])
        subject_raw = str(row["subject"] or "").strip()
        body_raw = str(row["body"] or "")
        subject = preview_text(subject_raw, 80) if subject_raw else "(no subject)"
        body = preview_text(body_raw, MESSAGE_BODY_PREVIEW_WIDTH)
        task_id = str(row["task_id"] or "").strip()
        task_link = f" task={task_id}" if task_id else ""
        print(f"        - {message_id} from {sender} at {created_at}{task_link}")
        print(f"          subject: {subject}")
        print(f"          body: {body}")

    remaining = unread_count - len(rows)
    if remaining > 0:
        print(f"        ... and {remaining} more unread CEO message(s).")


def wait_for_ceo_inbox_clear(
    conn: sqlite3.Connection,
    team_root: Path,
    round_number: int,
    total_rounds: int,
    *,
    ignore_ceo_messages: bool,
) -> bool:
    while True:
        unread_ceo = count_unread_messages(conn, "ceo")
        if unread_ceo == 0:
            return True

        if ignore_ceo_messages:
            print(
                f"[WARN] round={round_number}/{total_rounds} continuing: "
                f"CEO has {unread_ceo} unread message(s) "
                "(enabled by --ignore-ceo-messages)."
            )
            return True

        print(
            f"[PAUSE] round={round_number}/{total_rounds} blocked: "
            f"CEO has {unread_ceo} unread message(s)."
        )
        try:
            unread_rows = list_unread_messages(conn, "ceo", limit=CEO_UNREAD_PREVIEW_LIMIT)
        except sqlite3.Error as exc:
            unread_rows = []
            print(f"[WARN] unable to list unread CEO messages: {exc}", file=sys.stderr)
        else:
            print_unread_message_preview(unread_ceo, unread_rows)
        print(
            f"        Address CEO inbox first (hint: {team_root / 'ceo'} inbox), "
            "then press Enter to re-check."
        )
        print("        To continue without this gate, re-run with --ignore-ceo-messages.")

        if not sys.stdin.isatty():
            print(
                "[ERROR] stdin is not interactive; cannot prompt for CEO inbox gate.",
                file=sys.stderr,
            )
            return False

        try:
            response = input("        Continue? [Enter=re-check, q=quit]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return False

        if response in {"q", "quit", "exit"}:
            return False


def count_actionable_tasks(conn: sqlite3.Connection, member: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM tasks
        WHERE owner = ? AND state IN ('todo', 'in_progress')
        """,
        (member,),
    ).fetchone()
    return int(row["c"]) if row is not None else 0


def default_should_run(conn: sqlite3.Connection, member: str, team_root: Path) -> tuple[bool, str]:
    del team_root

    unread_count = count_unread_messages(conn, member)
    actionable_count = count_actionable_tasks(conn, member)

    if unread_count == 0 and actionable_count == 0:
        return False, "no unread messages and no todo/in_progress tasks"

    reasons: list[str] = []
    if unread_count > 0:
        reasons.append(f"{unread_count} unread message(s)")
    if actionable_count > 0:
        reasons.append(f"{actionable_count} todo/in_progress task(s)")
    return True, " and ".join(reasons)


SPECIAL_MEMBER_CHECKS: dict[str, ShouldRunCheck] = {
    # "member-name": should_run_member_name,
}
# TEAM_RUN_CUSTOM_CHECKS


def should_run_member(conn: sqlite3.Connection, member: str, team_root: Path) -> tuple[bool, str]:
    checker = SPECIAL_MEMBER_CHECKS.get(member)
    if checker is None:
        return default_should_run(conn, member, team_root)

    try:
        should_run, reason = checker(conn, member, team_root)
    except Exception as exc:
        return True, f"custom check failed ({exc!r}); running to avoid starvation"

    if not isinstance(should_run, bool):
        return True, "custom check returned non-bool decision; running to avoid starvation"

    clean_reason = (reason or "").strip() or "custom check"
    return should_run, clean_reason


def build_execute_prompt(member: str, team_root: Path) -> str:
    return (
        "Use $team in execute mode only. "
        f"Execute one work round for member '{member}' in team '{team_root}'. "
        "Follow mission/role/context loading, message-first processing, single-task handling, "
        "and runtime CLI state updates exactly as defined by the skill."
    )


def build_codex_command(
    codex_bin: str,
    project_root: Path,
    prompt: str,
    model: str,
    reasoning_effort: str,
    codex_args: list[str],
) -> list[str]:
    return [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--cd",
        str(project_root),
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        *codex_args,
        prompt,
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run each team member whose run criteria currently evaluate to true."
    )
    parser.add_argument(
        "--team",
        default=None,
        help=(
            "Team name or path. Defaults to the directory containing this script "
            "(expected TEAM_<name>/)."
        ),
    )
    parser.add_argument(
        "--member",
        action="append",
        default=[],
        help=(
            "Run only this member identity. Repeat to select multiple members. "
            "Member matching is case-insensitive."
        ),
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="Number of scheduler rounds to run (default: 1).",
    )
    parser.add_argument(
        "--codex-bin",
        default=os.environ.get("CODEX_BIN", "codex"),
        help="Codex CLI executable (default: CODEX_BIN env var or 'codex').",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.3-codex",
        help="Codex model to use for member runs (default: gpt-5.3-codex).",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_LEVELS,
        default="medium",
        help="Model reasoning effort (default: medium).",
    )
    parser.add_argument(
        "--codex-arg",
        action="append",
        default=[],
        help="Extra arg passed to `codex exec` before the prompt. Repeatable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned member runs but do not invoke Codex.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue to the next runnable member even if one run fails.",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run runnable members one at a time instead of concurrently.",
    )
    parser.add_argument(
        "--ignore-ceo-messages",
        action="store_true",
        help=(
            "Continue rounds even when CEO has unread inbox messages "
            "(default: gate on unread CEO messages)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit final summary as JSON.",
    )
    return parser.parse_args()


def print_command(command: list[str]) -> str:
    escaped = [json.dumps(part) for part in command]
    return " ".join(escaped)


def append_run_timestamp(team_root: Path, member_dir_name: str) -> None:
    run_path = team_root / "members" / member_dir_name / ".run"
    timestamp = datetime.now(timezone.utc).isoformat()
    with run_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp}\n")


def main() -> int:
    args = parse_args()
    if args.rounds <= 0:
        return fail("--rounds must be greater than 0.")

    default_team_root = Path(__file__).resolve().parent
    team_root = resolve_team_root(args.team, default_team_root)
    if not team_root.exists() or not team_root.is_dir():
        return fail(f"team directory not found: {team_root}")
    project_root = team_root.parent
    if not project_root.exists() or not project_root.is_dir():
        return fail(f"project directory not found: {project_root}")

    members = discover_members(team_root)
    if not members:
        return fail(f"no members found under: {team_root / 'members'}")

    selected_members: set[str]
    try:
        selected_members = {normalize_member(raw, "member filter") for raw in args.member}
    except ValueError as exc:
        return fail(str(exc))

    unknown = sorted(selected_members - set(members))
    if unknown:
        return fail(f"unknown member filter(s): {', '.join(unknown)}")

    member_keys = [key for key in members if not selected_members or key in selected_members]
    if not member_keys:
        return fail("no members selected to evaluate.")

    try:
        conn = connect_database(team_root)
    except FileNotFoundError as exc:
        return fail(str(exc))
    except sqlite3.Error as exc:
        return fail(f"unable to open team database: {exc}")

    summary: dict[str, list[dict[str, object]]] = {
        "ran": [],
        "skipped": [],
        "failed": [],
    }

    stop_after_round = False
    try:
        for round_number in range(1, args.rounds + 1):
            # Reset any active transaction so each round sees fresh runtime state.
            conn.commit()
            print(f"[ROUND] {round_number}/{args.rounds}")
            if not wait_for_ceo_inbox_clear(
                conn,
                team_root,
                round_number,
                args.rounds,
                ignore_ceo_messages=args.ignore_ceo_messages,
            ):
                print(
                    "[HINT] Re-run with --ignore-ceo-messages to continue rounds "
                    "even when CEO has unread messages."
                )
                summary["failed"].append(
                    {
                        "round": round_number,
                        "member": "ceo-gate",
                        "reason": "unread CEO messages require human handling",
                        "exit_code": None,
                        "error": "scheduler aborted by CEO inbox gate",
                    }
                )
                stop_after_round = True
                break

            launched: list[dict[str, object]] = []
            round_has_failure = False
            runnable_count = 0

            # Re-evaluate who should run at the start of each round.
            for member_key in member_keys:
                member_dir_name = members[member_key]
                should_run, reason = should_run_member(conn, member_key, team_root)

                if not should_run:
                    summary["skipped"].append(
                        {
                            "round": round_number,
                            "member": member_key,
                            "member_dir": member_dir_name,
                            "reason": reason,
                        }
                    )
                    print(f"[SKIP] round={round_number} {member_key}: {reason}")
                    continue

                runnable_count += 1
                prompt = build_execute_prompt(member_dir_name, team_root)
                command = build_codex_command(
                    args.codex_bin,
                    project_root,
                    prompt,
                    args.model,
                    args.reasoning_effort,
                    args.codex_arg,
                )
                command_display = print_command(command)

                if args.dry_run:
                    summary["ran"].append(
                        {
                            "round": round_number,
                            "member": member_key,
                            "member_dir": member_dir_name,
                            "reason": reason,
                            "dry_run": True,
                            "command": command,
                        }
                    )
                    print(f"[DRY-RUN] round={round_number} {member_key}: {reason}")
                    print(f"          {command_display}")
                    continue

                try:
                    append_run_timestamp(team_root, member_dir_name)
                except OSError as exc:
                    summary["failed"].append(
                        {
                            "round": round_number,
                            "member": member_key,
                            "member_dir": member_dir_name,
                            "reason": reason,
                            "exit_code": None,
                            "error": f"unable to append run timestamp: {exc}",
                        }
                    )
                    print(
                        f"[FAIL] round={round_number} {member_key}: "
                        f"unable to append .run timestamp ({exc})",
                        file=sys.stderr,
                    )
                    round_has_failure = True
                    if not args.continue_on_error:
                        stop_after_round = True
                        break
                    continue

                print(f"[RUN ] round={round_number} {member_key}: {reason}")
                print(f"          {command_display}")
                if args.sequential:
                    try:
                        returncode = subprocess.run(command, check=False).returncode
                    except OSError as exc:
                        summary["failed"].append(
                            {
                                "round": round_number,
                                "member": member_key,
                                "member_dir": member_dir_name,
                                "reason": reason,
                                "exit_code": None,
                                "error": str(exc),
                            }
                        )
                        print(f"[FAIL] round={round_number} {member_key}: {exc}", file=sys.stderr)
                        round_has_failure = True
                        if not args.continue_on_error:
                            stop_after_round = True
                            break
                        continue

                    if returncode == 0:
                        summary["ran"].append(
                            {
                                "round": round_number,
                                "member": member_key,
                                "member_dir": member_dir_name,
                                "reason": reason,
                                "dry_run": False,
                                "exit_code": 0,
                            }
                        )
                        print(f"[DONE] round={round_number} {member_key}")
                    else:
                        summary["failed"].append(
                            {
                                "round": round_number,
                                "member": member_key,
                                "member_dir": member_dir_name,
                                "reason": reason,
                                "exit_code": returncode,
                            }
                        )
                        print(
                            f"[FAIL] round={round_number} {member_key}: exit {returncode}",
                            file=sys.stderr,
                        )
                        round_has_failure = True
                        if not args.continue_on_error:
                            stop_after_round = True
                            break
                    continue

                try:
                    process = subprocess.Popen(command)
                except OSError as exc:
                    summary["failed"].append(
                        {
                            "round": round_number,
                            "member": member_key,
                            "member_dir": member_dir_name,
                            "reason": reason,
                            "exit_code": None,
                            "error": str(exc),
                        }
                    )
                    print(f"[FAIL] round={round_number} {member_key}: {exc}", file=sys.stderr)
                    round_has_failure = True
                    if not args.continue_on_error:
                        stop_after_round = True
                        break
                    continue

                launched.append(
                    {
                        "round": round_number,
                        "member": member_key,
                        "member_dir": member_dir_name,
                        "reason": reason,
                        "process": process,
                    }
                )

            if runnable_count == 0:
                print(
                    f"[ROUND] {round_number}/{args.rounds} "
                    "no members eligible to run; ending remaining rounds early."
                )
                stop_after_round = True

            if not args.sequential:
                # Barrier: wait for all launched member runs in this round before
                # evaluating run criteria for the next round.
                for launched_run in launched:
                    process = launched_run["process"]
                    assert isinstance(process, subprocess.Popen)
                    returncode = process.wait()
                    member_key = str(launched_run["member"])
                    member_dir_name = str(launched_run["member_dir"])
                    reason = str(launched_run["reason"])

                    if returncode == 0:
                        summary["ran"].append(
                            {
                                "round": round_number,
                                "member": member_key,
                                "member_dir": member_dir_name,
                                "reason": reason,
                                "dry_run": False,
                                "exit_code": 0,
                            }
                        )
                        print(f"[DONE] round={round_number} {member_key}")
                    else:
                        summary["failed"].append(
                            {
                                "round": round_number,
                                "member": member_key,
                                "member_dir": member_dir_name,
                                "reason": reason,
                                "exit_code": returncode,
                            }
                        )
                        print(
                            f"[FAIL] round={round_number} {member_key}: exit {returncode}",
                            file=sys.stderr,
                        )
                        round_has_failure = True

            if stop_after_round:
                break
            if round_has_failure and not args.continue_on_error:
                break
    finally:
        conn.close()

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"[SUMMARY] ran={len(summary['ran'])} "
            f"skipped={len(summary['skipped'])} "
            f"failed={len(summary['failed'])}"
        )

    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
