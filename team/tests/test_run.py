from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import team_cli


def load_run_module():
    spec = importlib.util.spec_from_file_location("team_run_test_module", SCRIPT_DIR / "run.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load run.py for tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUN = load_run_module()


class RunSchedulerTest(unittest.TestCase):
    def make_team(self) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)

        team_root = Path(tempdir.name) / "TEAM_demo"
        (team_root / "members" / "analyst").mkdir(parents=True)
        conn, _ = team_cli.ensure_database(team_root)
        conn.close()
        return team_root

    def test_rounds_negative_one_exits_when_no_members_are_runnable(self) -> None:
        team_root = self.make_team()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch.object(sys, "argv", ["run.py", "--team", str(team_root), "--rounds", "-1"]),
        ):
            exit_code = RUN.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn(
            "no members eligible to run; ending --rounds=-1 run gracefully.",
            stdout.getvalue(),
        )
        self.assertNotIn("rechecking in", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
