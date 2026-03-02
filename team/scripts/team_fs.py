#!/usr/bin/env python3
"""Filesystem helper for the team skill."""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

VALID_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
RUNNER_TEMPLATE_FILENAME = "run.py"
RUNNER_CUSTOM_MARKER = "# TEAM_RUN_CUSTOM_CHECKS"


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


def runner_template_path() -> Path:
    return Path(__file__).resolve().parent / RUNNER_TEMPLATE_FILENAME


def write_team_runner(team_root: Path, overwrite: bool) -> None:
    template_path = runner_template_path()
    if not template_path.exists() or not template_path.is_file():
        raise FileNotFoundError(f"team runner template not found: {template_path}")

    run_path = team_root / "run.py"
    if run_path.exists() and run_path.is_dir():
        raise ValueError(f"runner target exists as a directory: {run_path}")
    if run_path.exists() and not overwrite:
        print(f"[SKIP] runner exists: {run_path}")
        return

    run_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
    run_path.chmod(0o755)
    print(f"[OK] wrote runner: {run_path}")


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
    run_path = team_root / "run.py"
    if not run_path.exists():
        write_team_runner(team_root, overwrite=False)
    if not run_path.exists() or not run_path.is_file():
        raise FileNotFoundError(f"team runner not found: {run_path}")

    member_id = member_identity(member)
    registration = f'SPECIAL_MEMBER_CHECKS["{member_id}"] = '

    source = run_path.read_text(encoding="utf-8")
    if registration in source:
        print(f"[SKIP] custom run check already exists for member '{member_id}': {run_path}")
        return
    if RUNNER_CUSTOM_MARKER not in source:
        raise ValueError(
            f"runner is missing expected marker '{RUNNER_CUSTOM_MARKER}': {run_path}"
        )

    snippet = build_custom_run_check_snippet(member_id, criteria)
    updated = source.replace(RUNNER_CUSTOM_MARKER, f"{snippet}{RUNNER_CUSTOM_MARKER}", 1)
    run_path.write_text(updated, encoding="utf-8")
    print(f"[OK] added custom run check for member '{member_id}': {run_path}")


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
        write_team_runner(team_root, overwrite=args.overwrite_runner)
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
        "--overwrite-runner",
        action="store_true",
        help="Overwrite TEAM_<name>/run.py if it already exists.",
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
            "TEAM_<name>/run.py is updated with a custom check stub for this member."
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
