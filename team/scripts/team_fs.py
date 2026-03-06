#!/usr/bin/env python3
"""Filesystem helper for the team skill."""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

VALID_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
RUN_WRAPPER_FILENAME = "run"
RUN_WRAPPER_CUSTOM_MARKER = "# TEAM_RUN_WRAPPER_CUSTOM_CHECKS"


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


def role_template(role: str) -> str:
    role_text = role.strip() or "TODO: define this member's role and constraints."
    return f"# Role\n{role_text}\n"


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
        "import os\n"
        "import re\n"
        "import sqlite3\n"
        "import subprocess\n"
        "import sys\n"
        "from pathlib import Path\n"
        "from typing import Callable\n\n"
        'VALID_MEMBER = re.compile(r"^[A-Za-z0-9._-]+$")\n'
        'DB_FILENAME = "team_state.sqlite3"\n'
        "ShouldRunCheck = Callable[[sqlite3.Connection, str, Path], tuple[bool, str]]\n"
        f"TEAM_ROOT = Path({team_root_literal}).resolve()\n\n"
        "def normalize_member(value: str, label: str = \"member\") -> str:\n"
        "    member = value.strip()\n"
        "    if not member:\n"
        "        raise ValueError(f\"{label} cannot be empty.\")\n"
        "    if \"/\" in member or \"\\\\\" in member:\n"
        "        raise ValueError(f\"{label} cannot contain path separators: {value!r}\")\n"
        "    if not VALID_MEMBER.match(member):\n"
        "        raise ValueError(\n"
        "            f\"{label} must match {VALID_MEMBER.pattern} (letters, numbers, ., _, -).\"\n"
        "        )\n"
        "    return member.lower()\n\n"
        "def discover_members(team_root: Path) -> dict[str, str]:\n"
        "    members_dir = team_root / \"members\"\n"
        "    if not members_dir.is_dir():\n"
        "        return {}\n\n"
        "    members: dict[str, str] = {}\n"
        "    for child in sorted(members_dir.iterdir(), key=lambda path: path.name.lower()):\n"
        "        if not child.is_dir():\n"
        "            continue\n"
        "        try:\n"
        "            member_key = normalize_member(child.name)\n"
        "        except ValueError:\n"
        "            continue\n"
        "        if member_key in members:\n"
        "            continue\n"
        "        members[member_key] = child.name\n"
        "    return dict(sorted(members.items()))\n\n"
        "def connect_database(team_root: Path) -> sqlite3.Connection:\n"
        "    db_path = team_root / \"state\" / DB_FILENAME\n"
        "    if not db_path.exists():\n"
        "        raise FileNotFoundError(f\"team state database not found: {db_path}\")\n\n"
        "    conn = sqlite3.connect(db_path, timeout=30.0)\n"
        "    conn.row_factory = sqlite3.Row\n"
        "    conn.execute(\"PRAGMA busy_timeout=30000;\")\n"
        "    return conn\n\n"
        "def count_unread_messages(conn: sqlite3.Connection, member: str) -> int:\n"
        "    row = conn.execute(\n"
        "        \"\"\"\n"
        "        SELECT COUNT(*) AS c\n"
        "        FROM messages\n"
        "        WHERE receiver = ? AND status = 'unread'\n"
        "        \"\"\",\n"
        "        (member,),\n"
        "    ).fetchone()\n"
        "    return int(row[\"c\"]) if row is not None else 0\n\n"
        "def count_actionable_tasks(conn: sqlite3.Connection, member: str) -> int:\n"
        "    row = conn.execute(\n"
        "        \"\"\"\n"
        "        SELECT COUNT(*) AS c\n"
        "        FROM tasks\n"
        "        WHERE owner = ? AND state IN ('todo', 'in_progress')\n"
        "        \"\"\",\n"
        "        (member,),\n"
        "    ).fetchone()\n"
        "    return int(row[\"c\"]) if row is not None else 0\n\n"
        "def default_should_run(conn: sqlite3.Connection, member: str, team_root: Path) -> tuple[bool, str]:\n"
        "    del team_root\n"
        "    unread_count = count_unread_messages(conn, member)\n"
        "    actionable_count = count_actionable_tasks(conn, member)\n\n"
        "    if unread_count == 0 and actionable_count == 0:\n"
        "        return False, \"no unread messages and no todo/in_progress tasks\"\n\n"
        "    reasons: list[str] = []\n"
        "    if unread_count > 0:\n"
        "        reasons.append(f\"{unread_count} unread message(s)\")\n"
        "    if actionable_count > 0:\n"
        "        reasons.append(f\"{actionable_count} todo/in_progress task(s)\")\n"
        "    return True, \" and \".join(reasons)\n\n"
        "SPECIAL_MEMBER_CHECKS: dict[str, ShouldRunCheck] = {\n"
        "    # \"member-name\": should_run_member_name,\n"
        "}\n"
        f"{RUN_WRAPPER_CUSTOM_MARKER}\n\n"
        "def should_run_member(conn: sqlite3.Connection, member: str, team_root: Path) -> tuple[bool, str]:\n"
        "    checker = SPECIAL_MEMBER_CHECKS.get(member)\n"
        "    if checker is None:\n"
        "        return default_should_run(conn, member, team_root)\n\n"
        "    try:\n"
        "        should_run, reason = checker(conn, member, team_root)\n"
        "    except Exception as exc:\n"
        "        return True, f\"custom check failed ({exc!r}); running to avoid starvation\"\n\n"
        "    if not isinstance(should_run, bool):\n"
        "        return True, \"custom check returned non-bool decision; running to avoid starvation\"\n\n"
        "    clean_reason = (reason or \"\").strip() or \"custom check\"\n"
        "    return should_run, clean_reason\n\n"
        "def collect_custom_member_filters(team_root: Path, members: dict[str, str]) -> tuple[set[str], set[str]]:\n"
        "    if not SPECIAL_MEMBER_CHECKS:\n"
        "        return set(), set()\n\n"
        "    allow_members: set[str] = set()\n"
        "    deny_members: set[str] = set()\n"
        "    conn = connect_database(team_root)\n"
        "    try:\n"
        "        for member_key in sorted(SPECIAL_MEMBER_CHECKS):\n"
        "            if member_key not in members:\n"
        "                print(\n"
        "                    f\"[WARN] custom run check references missing member '{member_key}'; skipping.\",\n"
        "                    file=sys.stderr,\n"
        "                )\n"
        "                continue\n"
        "            should_run, reason = should_run_member(conn, member_key, team_root)\n"
        "            decision = \"allow\" if should_run else \"deny\"\n"
        "            print(f\"[WRAP] custom decision {member_key}: {decision} ({reason})\", flush=True)\n"
        "            if should_run:\n"
        "                allow_members.add(member_key)\n"
        "            else:\n"
        "                deny_members.add(member_key)\n"
        "    finally:\n"
        "        conn.close()\n\n"
        "    return allow_members, deny_members\n\n"
        "def resolve_run_script() -> Path:\n"
        "    codex_home = Path(os.environ.get(\"CODEX_HOME\", str(Path.home() / \".codex\")))\n"
        "    return (codex_home / \"skills\" / \"team\" / \"scripts\" / \"run.py\").resolve()\n\n"
        "def main() -> int:\n"
        "    if not TEAM_ROOT.exists() or not TEAM_ROOT.is_dir():\n"
        "        print(f\"[ERROR] team directory not found: {TEAM_ROOT}\", file=sys.stderr)\n"
        "        return 1\n\n"
        "    forwarded_args = list(sys.argv[1:])\n"
        "    help_requested = any(arg in {\"-h\", \"--help\"} for arg in forwarded_args)\n"
        "    allow_members: set[str] = set()\n"
        "    deny_members: set[str] = set()\n"
        "    if not help_requested:\n"
        "        members = discover_members(TEAM_ROOT)\n"
        "        try:\n"
        "            allow_members, deny_members = collect_custom_member_filters(TEAM_ROOT, members)\n"
        "        except (FileNotFoundError, sqlite3.Error, ValueError) as exc:\n"
        "            print(f\"[ERROR] unable to evaluate custom run checks: {exc}\", file=sys.stderr)\n"
        "            return 1\n\n"
        "        overlap = sorted(allow_members & deny_members)\n"
        "        if overlap:\n"
        "            joined = \", \".join(overlap)\n"
        "            print(\n"
        "                f\"[ERROR] custom checks produced conflicting allow/deny decisions: {joined}\",\n"
        "                file=sys.stderr,\n"
        "            )\n"
        "            return 1\n\n"
        "    run_script = resolve_run_script()\n"
        "    if not run_script.exists() or not run_script.is_file():\n"
        "        print(f\"[ERROR] team run script not found: {run_script}\", file=sys.stderr)\n"
        "        return 1\n\n"
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
        ") -> tuple[bool, str]:\n"
        f"    \"\"\"Custom run rule for '{member_id}'.\"\"\"\n"
        "    # Recruit-time criteria:\n"
        f"{criteria_comment}\n"
        "    # TODO: replace fallback with this member's specific run criteria.\n"
        "    return default_should_run(conn, member, team_root)\n"
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


def resolve_team_root(team: str, base: Path) -> Path:
    team_path = Path(team)

    if team_path.is_absolute():
        return team_path.resolve()

    if len(team_path.parts) > 1 or team.startswith("."):
        return (base / team_path).resolve()

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create teams and recruit team members for the team skill."
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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
