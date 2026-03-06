#!/usr/bin/env python3
"""Human-only CEO terminal UI for inspecting team state and replying to messages.

This tool is intentionally blocked in Codex agent runtime environments.
"""

from __future__ import annotations

import argparse
import os
import re
import select
import shutil
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, NamedTuple

import team_cli as runtime

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - non-POSIX fallback
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]

TASK_SCOPE_CHOICES = ("open", "all", *runtime.TASK_STATES)
MESSAGE_SCOPE_CHOICES = runtime.MESSAGE_LIST_SCOPES
MESSAGE_SCOPE_CYCLE = ("all", "inbox", "unread", "read", "archived")
TASK_DISPLAY_STATE_ORDER = {
    "todo": 0,
    "done": 1,
    "cancelled": 2,
}
DEFAULT_TABLE_LIMIT = 200

KEY_UP = "up"
KEY_DOWN = "down"
KEY_LEFT = "left"
KEY_RIGHT = "right"
KEY_ENTER = "enter"
KEY_ESCAPE = "escape"
KEY_PAGE_UP = "page_up"
KEY_PAGE_DOWN = "page_down"
KEY_QUIT = "quit"
KEY_BACK = "back"
KEY_FORWARD = "forward"
KEY_REPLY = "reply"
KEY_CTRL_Q = "ctrl_q"
KEY_CTRL_S = "ctrl_s"
KEY_BACKSPACE = "backspace"
KEY_F1 = "f1"
KEY_F2 = "f2"

ACTION_SELECT = "select"
ACTION_CANCEL = "cancel"
ACTION_BACK = "back"
ACTION_FORWARD = "forward"
ACTION_OPEN = "open"
ACTION_STAY = "stay"
ACTION_QUIT = "quit"
ACTION_FILTER_TEXT = "filter_text"
ACTION_FILTER_OWNER = "filter_owner"
ACTION_FILTER_ORIGIN = "filter_origin"
ACTION_FILTER_DESTINATION = "filter_destination"
ACTION_FILTER_SCOPE = "filter_scope"
ACTION_FILTER_LIMIT = "filter_limit"
ACTION_FILTER_CLEAR = "filter_clear"
ACTION_ARCHIVE_HOVERED = "archive_hovered"
ACTION_UNARCHIVE_HOVERED = "unarchive_hovered"

SCREEN_MENU = "menu"
SCREEN_TASK_LIST = "task_list"
SCREEN_TASK_DETAIL = "task_detail"
SCREEN_MESSAGE_LIST = "message_list"
SCREEN_MESSAGE_DETAIL = "message_detail"

ID_TOKEN_RE = re.compile(r"^[0-9a-fA-F-]{2,36}$")


class SelectionResult(NamedTuple):
    action: str
    index: int | None = None


@dataclass(frozen=True)
class ScreenEntry:
    kind: str
    params: tuple[object, ...] = ()


@dataclass
class ScreenResult:
    action: str
    screen: ScreenEntry | None = None


class ScreenHistory:
    def __init__(self) -> None:
        self._entries: list[ScreenEntry] = []
        self._index = -1

    def current(self) -> ScreenEntry | None:
        if self._index < 0:
            return None
        return self._entries[self._index]

    def visit(self, entry: ScreenEntry) -> None:
        current = self.current()
        if current == entry:
            return
        if self._index < len(self._entries) - 1:
            self._entries = self._entries[: self._index + 1]
        self._entries.append(entry)
        self._index = len(self._entries) - 1

    def back(self) -> ScreenEntry | None:
        if self._index <= 0:
            return None
        self._index -= 1
        return self._entries[self._index]

    def forward(self) -> ScreenEntry | None:
        if self._index >= len(self._entries) - 1:
            return None
        self._index += 1
        return self._entries[self._index]


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


def short_id(value: str) -> str:
    return value[-6:]


def render_text(value: object) -> str:
    return str(value or "").replace("\\n", "\n")


def supports_interactive_navigation() -> bool:
    return (
        termios is not None
        and tty is not None
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


class RawKeyboardSession:
    def __init__(self) -> None:
        self.fd: int | None = None
        self._old_termios: list[object] | None = None

    def __enter__(self) -> int:
        if not supports_interactive_navigation():
            raise RuntimeError("Interactive keyboard mode is unavailable on this terminal.")
        self.fd = sys.stdin.fileno()
        self._old_termios = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        print("\033[?25l", end="", flush=True)
        return self.fd

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None and self._old_termios is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_termios)
        print("\033[?25h", end="", flush=True)


def read_keypress(fd: int) -> str:
    first = os.read(fd, 1)
    if first in {b"\r", b"\n"}:
        return KEY_ENTER
    if first in {b"\x03"}:
        raise KeyboardInterrupt
    if first in {b"q", b"Q"}:
        return KEY_QUIT
    if first in {b"b", b"B"}:
        return KEY_BACK
    if first in {b"f", b"F"}:
        return KEY_FORWARD
    if first in {b"r", b"R"}:
        return KEY_REPLY
    if first in {b"k", b"K"}:
        return KEY_UP
    if first in {b"j", b"J"}:
        return KEY_DOWN

    if first != b"\x1b":
        if first.isdigit():
            return first.decode("ascii")
        try:
            char = first.decode("utf-8").lower()
        except UnicodeDecodeError:
            return ""
        if char.isprintable():
            return char
        return ""

    ready, _, _ = select.select([fd], [], [], 0.02)
    if not ready:
        return KEY_ESCAPE

    second = os.read(fd, 1)
    if second not in {b"[", b"O"}:
        return KEY_ESCAPE

    ready, _, _ = select.select([fd], [], [], 0.02)
    if not ready:
        return KEY_ESCAPE

    third = os.read(fd, 1)
    if third == b"A":
        return KEY_UP
    if third == b"B":
        return KEY_DOWN
    if third == b"C":
        return KEY_RIGHT
    if third == b"D":
        return KEY_LEFT
    if third == b"5":
        ready, _, _ = select.select([fd], [], [], 0.02)
        if ready:
            os.read(fd, 1)
        return KEY_PAGE_UP
    if third == b"6":
        ready, _, _ = select.select([fd], [], [], 0.02)
        if ready:
            os.read(fd, 1)
        return KEY_PAGE_DOWN
    return ""


def read_editor_key(fd: int) -> tuple[str, str]:
    first = os.read(fd, 1)
    if first in {b"\x03"}:
        raise KeyboardInterrupt
    if first in {b"\x11"}:
        return KEY_CTRL_Q, ""
    if first in {b"\x13"}:
        return KEY_CTRL_S, ""
    if first in {b"\r", b"\n"}:
        return KEY_ENTER, ""
    if first in {b"\x08", b"\x7f"}:
        return KEY_BACKSPACE, ""
    if first in {b"\t"}:
        return "char", "    "

    if first == b"\x1b":
        ready, _, _ = select.select([fd], [], [], 0.02)
        if not ready:
            return KEY_ESCAPE, ""

        second = os.read(fd, 1)
        if second not in {b"[", b"O"}:
            return KEY_ESCAPE, ""

        ready, _, _ = select.select([fd], [], [], 0.02)
        if not ready:
            return KEY_ESCAPE, ""

        third = os.read(fd, 1)
        if second == b"O":
            if third == b"P":
                return KEY_F1, ""
            if third == b"Q":
                return KEY_F2, ""
            if third == b"A":
                return KEY_UP, ""
            if third == b"B":
                return KEY_DOWN, ""
            if third == b"C":
                return KEY_RIGHT, ""
            if third == b"D":
                return KEY_LEFT, ""
            return "", ""

        if third == b"A":
            return KEY_UP, ""
        if third == b"B":
            return KEY_DOWN, ""
        if third == b"C":
            return KEY_RIGHT, ""
        if third == b"D":
            return KEY_LEFT, ""
        if third.isdigit():
            sequence = third.decode("ascii")
            terminator = ""
            for _ in range(4):
                ready, _, _ = select.select([fd], [], [], 0.02)
                if not ready:
                    break
                ch = os.read(fd, 1)
                if not ch:
                    break
                decoded = ch.decode("ascii", errors="ignore")
                if decoded in "~":
                    terminator = decoded
                    break
                if decoded.isdigit():
                    sequence += decoded
                else:
                    terminator = decoded
                    break
            token = f"{sequence}{terminator}"
            if token == "5~":
                return KEY_PAGE_UP, ""
            if token == "6~":
                return KEY_PAGE_DOWN, ""
            if token == "11~":
                return KEY_F1, ""
            if token == "12~":
                return KEY_F2, ""
        return "", ""

    try:
        char = first.decode("utf-8")
    except UnicodeDecodeError:
        return "", ""

    if char.isprintable():
        return "char", char
    return "", ""


def style_selected(line: str) -> str:
    return f"\033[7m{line}\033[0m"


def terminal_lines(default: int = 24) -> int:
    return shutil.get_terminal_size(fallback=(100, default)).lines


def compute_window_start(
    selected_index: int,
    total_items: int,
    window_size: int,
    current_top: int,
) -> int:
    if total_items <= window_size:
        return 0
    if selected_index < current_top:
        return selected_index
    if selected_index >= current_top + window_size:
        return selected_index - window_size + 1
    return current_top


def prompt_record_selection_text(label: str, rows: list[sqlite3.Row], id_key: str) -> int | None:
    total = len(rows)
    while True:
        raw = input(
            f"{label} selection (1-{total}, full ID, or last 6 chars; blank to return): "
        ).strip()
        if not raw:
            return None

        try:
            selected = int(raw)
        except ValueError:
            selected = None
        if selected is not None and 1 <= selected <= total:
            return selected - 1

        full_matches = [
            index for index, row in enumerate(rows) if str(row[id_key]).strip() == raw
        ]
        if len(full_matches) == 1:
            return full_matches[0]
        if len(full_matches) > 1:
            print("Selection is ambiguous. Enter a row number or full ID.")
            continue

        if len(raw) == 6:
            suffix_matches = [
                index for index, row in enumerate(rows) if str(row[id_key]).endswith(raw)
            ]
            if len(suffix_matches) == 1:
                return suffix_matches[0]
            if len(suffix_matches) > 1:
                print("That last-6 ID is ambiguous. Enter a row number or full ID.")
                continue

        print(f"Enter a valid row number, full ID, or last 6 characters of the ID.")


def interactive_menu_selection(
    title_lines: list[str],
    options: list[str],
    prompt: str = "Use Up/Down and Enter. Press q to go back.",
) -> SelectionResult:
    if not options:
        return SelectionResult(ACTION_CANCEL, None)

    if not supports_interactive_navigation():
        while True:
            clear_screen()
            for line in title_lines:
                print(line)
            print()
            for index, option in enumerate(options, start=1):
                print(f"{index}) {option}")
            print("q) Back")
            raw = input("\nSelect action: ").strip().lower()
            if raw in {"q", "quit", "exit", ""}:
                return SelectionResult(ACTION_CANCEL, None)
            if raw in {"b", "back"}:
                return SelectionResult(ACTION_BACK, None)
            if raw in {"f", "forward"}:
                return SelectionResult(ACTION_FORWARD, None)
            try:
                selected = int(raw)
            except ValueError:
                selected = None
            if selected is not None and 1 <= selected <= len(options):
                return SelectionResult(ACTION_SELECT, selected - 1)

    selected_index = 0
    top = 0
    with RawKeyboardSession() as fd:
        while True:
            clear_screen()
            for line in title_lines:
                print(line)
            print()

            available_rows = max(1, terminal_lines() - len(title_lines) - 4)
            top = compute_window_start(selected_index, len(options), available_rows, top)
            end = min(len(options), top + available_rows)

            if top > 0:
                print(f"... {top} more above ...")
            for index in range(top, end):
                prefix = ">" if index == selected_index else " "
                row = f"{prefix} {index + 1}. {options[index]}"
                print(style_selected(row) if index == selected_index else row)
            if end < len(options):
                print(f"... {len(options) - end} more below ...")

            print()
            print(prompt)

            key = read_keypress(fd)
            if key == KEY_UP:
                selected_index = (selected_index - 1) % len(options)
            elif key == KEY_DOWN:
                selected_index = (selected_index + 1) % len(options)
            elif key == KEY_PAGE_UP:
                selected_index = max(0, selected_index - available_rows)
            elif key == KEY_PAGE_DOWN:
                selected_index = min(len(options) - 1, selected_index + available_rows)
            elif key == KEY_ENTER:
                return SelectionResult(ACTION_SELECT, selected_index)
            elif key == KEY_BACK:
                return SelectionResult(ACTION_BACK, None)
            elif key == KEY_FORWARD:
                return SelectionResult(ACTION_FORWARD, None)
            elif key in {KEY_ESCAPE, KEY_QUIT}:
                return SelectionResult(ACTION_CANCEL, None)
            elif key.isdigit():
                typed = int(key)
                if 1 <= typed <= len(options):
                    selected_index = typed - 1


def build_table_lines(headers: list[str], rows: list[list[str]]) -> tuple[str, str, list[str]]:
    widths = [len(header) for header in headers]
    normalized_rows: list[list[str]] = []
    for row in rows:
        normalized = [str(value).replace("\n", " ") for value in row]
        normalized_rows.append(normalized)
        for index, value in enumerate(normalized):
            widths[index] = max(widths[index], len(value))

    header_line = " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    separator_line = "-+-".join("-" * width for width in widths)
    row_lines = [
        " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in normalized_rows
    ]
    return header_line, separator_line, row_lines


def interactive_table_selection(
    title_lines: list[str],
    headers: list[str],
    rows: list[list[str]],
    label: str,
    raw_rows: list[sqlite3.Row],
    id_key: str,
    hotkeys: dict[str, str] | None = None,
    hotkey_help: str | None = None,
    initial_index: int = 0,
) -> SelectionResult:
    if not supports_interactive_navigation():
        if not rows:
            return SelectionResult(ACTION_CANCEL, None)
        print_table(headers, rows)
        selected = prompt_record_selection_text(label, raw_rows, id_key)
        if selected is None:
            return SelectionResult(ACTION_CANCEL, None)
        return SelectionResult(ACTION_SELECT, selected)

    if rows:
        selected_index = max(0, min(initial_index, len(rows) - 1))
    else:
        selected_index = 0
    top = 0
    header_line, separator_line, row_lines = build_table_lines(headers, rows)
    row_count = len(row_lines)

    with RawKeyboardSession() as fd:
        while True:
            clear_screen()
            for line in title_lines:
                print(line)
            print()
            print(header_line)
            print(separator_line)

            fixed_lines = len(title_lines) + 6 + (1 if hotkey_help else 0)
            available_rows = max(1, terminal_lines() - fixed_lines)
            top = compute_window_start(selected_index, row_count, available_rows, top)
            end = min(row_count, top + available_rows)

            if row_count == 0:
                print("(no rows)")
            else:
                if top > 0:
                    print(f"... {top} more above ...")
                for index in range(top, end):
                    prefix = ">" if index == selected_index else " "
                    rendered = f"{prefix} {row_lines[index]}"
                    print(style_selected(rendered) if index == selected_index else rendered)
                if end < row_count:
                    print(f"... {row_count - end} more below ...")

            print()
            print(f"Use Up/Down and Enter to open a {label}. Press b/f for history, q to return.")
            if hotkey_help:
                print(hotkey_help)

            key = read_keypress(fd)
            if key == KEY_UP:
                if row_count > 0:
                    selected_index = (selected_index - 1) % row_count
            elif key == KEY_DOWN:
                if row_count > 0:
                    selected_index = (selected_index + 1) % row_count
            elif key == KEY_PAGE_UP:
                if row_count > 0:
                    selected_index = max(0, selected_index - available_rows)
            elif key == KEY_PAGE_DOWN:
                if row_count > 0:
                    selected_index = min(row_count - 1, selected_index + available_rows)
            elif key == KEY_ENTER:
                if row_count == 0:
                    continue
                return SelectionResult(ACTION_SELECT, selected_index)
            elif key == KEY_BACK:
                return SelectionResult(ACTION_BACK, None)
            elif key == KEY_FORWARD:
                return SelectionResult(ACTION_FORWARD, None)
            elif key in {KEY_ESCAPE, KEY_QUIT}:
                return SelectionResult(ACTION_CANCEL, None)
            elif hotkeys is not None and key in hotkeys:
                return SelectionResult(hotkeys[key], selected_index if row_count > 0 else None)
            elif key.isdigit():
                typed = int(key)
                if 1 <= typed <= row_count:
                    selected_index = typed - 1


def line_token_bounds(line: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in re.finditer(r"\S+", line)]


def first_token_position(tokens_by_line: list[list[tuple[int, int]]]) -> tuple[int, int]:
    for line_index, tokens in enumerate(tokens_by_line):
        if tokens:
            return line_index, 0
    return 0, -1


def move_horizontal_token(
    tokens_by_line: list[list[tuple[int, int]]],
    line_index: int,
    token_index: int,
    step: int,
) -> tuple[int, int]:
    if token_index < 0:
        return first_token_position(tokens_by_line)

    new_line = line_index
    new_token = token_index + step
    if step < 0:
        while new_line >= 0:
            tokens = tokens_by_line[new_line]
            if 0 <= new_token < len(tokens):
                return new_line, new_token
            new_line -= 1
            if new_line >= 0:
                new_token = len(tokens_by_line[new_line]) - 1
    else:
        total_lines = len(tokens_by_line)
        while new_line < total_lines:
            tokens = tokens_by_line[new_line]
            if 0 <= new_token < len(tokens):
                return new_line, new_token
            new_line += 1
            if new_line < total_lines:
                new_token = 0
    return line_index, token_index


def move_vertical_token(
    tokens_by_line: list[list[tuple[int, int]]],
    line_index: int,
    token_index: int,
    step: int,
) -> tuple[int, int]:
    if not tokens_by_line:
        return 0, -1
    target_line = max(0, min(len(tokens_by_line) - 1, line_index + step))
    tokens = tokens_by_line[target_line]
    if not tokens:
        return target_line, -1
    if token_index < 0:
        return target_line, 0
    return target_line, min(token_index, len(tokens) - 1)


def highlighted_line(
    line: str,
    tokens: list[tuple[int, int]],
    selected_token: int,
) -> str:
    if selected_token < 0 or selected_token >= len(tokens):
        return line
    start, end = tokens[selected_token]
    return f"{line[:start]}\033[7m{line[start:end]}\033[0m{line[end:]}"


def render_editor_line_with_cursor(line: str, cursor_col: int) -> str:
    col = max(0, min(cursor_col, len(line)))
    if not line:
        return "\033[7m \033[0m"
    if col >= len(line):
        return f"{line}\033[7m \033[0m"
    return f"{line[:col]}\033[7m{line[col]}\033[0m{line[col + 1:]}"


def normalize_reference_token(token: str) -> str:
    return token.strip("`'\".,;:()[]{}<>…")


def resolve_reference_target(
    conn: sqlite3.Connection,
    raw_token: str,
) -> ScreenEntry | None:
    token = normalize_reference_token(raw_token)
    if not token:
        return None
    token_lower = token.lower()

    exact_task = conn.execute(
        "SELECT task_id FROM tasks WHERE lower(task_id) = ? LIMIT 1",
        (token_lower,),
    ).fetchone()
    exact_message = conn.execute(
        "SELECT message_id FROM messages WHERE lower(message_id) = ? LIMIT 1",
        (token_lower,),
    ).fetchone()

    if exact_task and not exact_message:
        return ScreenEntry(SCREEN_TASK_DETAIL, (exact_task["task_id"],))
    if exact_message and not exact_task:
        return ScreenEntry(SCREEN_MESSAGE_DETAIL, (exact_message["message_id"],))
    if exact_task and exact_message:
        return None

    if not ID_TOKEN_RE.match(token_lower):
        return None

    suffix = f"%{token_lower}"
    task_matches = conn.execute(
        "SELECT task_id FROM tasks WHERE lower(task_id) LIKE ? ORDER BY task_id ASC LIMIT 3",
        (suffix,),
    ).fetchall()
    message_matches = conn.execute(
        "SELECT message_id FROM messages WHERE lower(message_id) LIKE ? ORDER BY message_id ASC LIMIT 3",
        (suffix,),
    ).fetchall()

    total_matches = len(task_matches) + len(message_matches)
    if total_matches != 1:
        return None
    if task_matches:
        return ScreenEntry(SCREEN_TASK_DETAIL, (task_matches[0]["task_id"],))
    return ScreenEntry(SCREEN_MESSAGE_DETAIL, (message_matches[0]["message_id"],))


def interactive_readonly_view(
    conn: sqlite3.Connection,
    title_lines: list[str],
    content_lines: list[str],
    can_reply: bool = False,
) -> ScreenResult:
    if not supports_interactive_navigation():
        clear_screen()
        for line in title_lines:
            print(line)
        print()
        for line in content_lines:
            print(line)
        if can_reply:
            print("\nReply is available from this view only in interactive mode.")
        pause()
        return ScreenResult(ACTION_CANCEL)

    tokens_by_line = [line_token_bounds(line) for line in content_lines]
    line_index, token_index = first_token_position(tokens_by_line)
    top = 0

    with RawKeyboardSession() as fd:
        while True:
            clear_screen()
            for line in title_lines:
                print(line)
            print()

            fixed_lines = len(title_lines) + 4
            view_height = max(1, terminal_lines() - fixed_lines)
            top = compute_window_start(line_index, len(content_lines), view_height, top)
            end = min(len(content_lines), top + view_height)

            if top > 0:
                print(f"... {top} lines above ...")
            for index in range(top, end):
                line = content_lines[index]
                tokens = tokens_by_line[index]
                if index == line_index:
                    rendered = highlighted_line(line, tokens, token_index)
                else:
                    rendered = line
                print(rendered)
            if end < len(content_lines):
                print(f"... {len(content_lines) - end} lines below ...")

            controls = "Arrows scroll cursor | Enter open hovered ID | b/f history | q close"
            if can_reply:
                controls += " | r reply"
            print()
            print(controls)

            key = read_keypress(fd)
            if key == KEY_UP:
                line_index, token_index = move_vertical_token(
                    tokens_by_line, line_index, token_index, -1
                )
            elif key == KEY_DOWN:
                line_index, token_index = move_vertical_token(
                    tokens_by_line, line_index, token_index, 1
                )
            elif key == KEY_LEFT:
                line_index, token_index = move_horizontal_token(
                    tokens_by_line, line_index, token_index, -1
                )
            elif key == KEY_RIGHT:
                line_index, token_index = move_horizontal_token(
                    tokens_by_line, line_index, token_index, 1
                )
            elif key == KEY_PAGE_UP:
                line_index, token_index = move_vertical_token(
                    tokens_by_line, line_index, token_index, -view_height
                )
            elif key == KEY_PAGE_DOWN:
                line_index, token_index = move_vertical_token(
                    tokens_by_line, line_index, token_index, view_height
                )
            elif key == KEY_BACK:
                return ScreenResult(ACTION_BACK)
            elif key == KEY_FORWARD:
                return ScreenResult(ACTION_FORWARD)
            elif key in {KEY_ESCAPE, KEY_QUIT}:
                return ScreenResult(ACTION_CANCEL)
            elif key == KEY_REPLY and can_reply:
                return ScreenResult("reply")
            elif key == KEY_ENTER:
                if token_index < 0:
                    continue
                tokens = tokens_by_line[line_index]
                if token_index >= len(tokens):
                    continue
                start, end = tokens[token_index]
                token = content_lines[line_index][start:end]
                target = resolve_reference_target(conn, token)
                if target is None:
                    continue
                return ScreenResult(ACTION_SELECT, target)

    return ScreenResult(ACTION_CANCEL)


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
            widths[index] = max(widths[index], max((len(line) for line in value.splitlines()), default=0))

    header_line = " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    separator_line = "-+-".join("-" * width for width in widths)
    print(header_line)
    print(separator_line)
    for row in rows:
        wrapped = [value.splitlines() or [""] for value in row]
        height = max(len(lines) for lines in wrapped)
        for line_index in range(height):
            line_cells = [
                wrapped[col_index][line_index] if line_index < len(wrapped[col_index]) else ""
                for col_index in range(len(headers))
            ]
            print(
                " | ".join(
                    line_cells[index].ljust(widths[index]) for index in range(len(headers))
                )
            )


def format_timestamp_human(timestamp: str) -> str:
    try:
        normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return timestamp
    return parsed.strftime("%Y-%d-%m %H:%M:%S")


def sort_task_rows_for_display(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    def sort_key(row: sqlite3.Row) -> tuple[object, ...]:
        state = render_text(row["state"]).strip().lower()
        state_rank = TASK_DISPLAY_STATE_ORDER.get(state, len(TASK_DISPLAY_STATE_ORDER))
        return (
            render_text(row["owner"]).strip().lower(),
            state_rank,
            state,
            -int(row["priority"]),
            render_text(row["created_at"]),
            render_text(row["task_id"]),
        )

    return sorted(rows, key=sort_key)


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
        print(f"{key}: {render_text(row[key])}")
    print("body:")
    print(render_text(row["body"]))


def view_all_tasks(conn: sqlite3.Connection) -> None:
    clear_screen()
    print("View All Tasks")
    scope = prompt_scope("Task scope", TASK_SCOPE_CHOICES, "all")
    limit = prompt_int("Limit", 100)

    rows = sort_task_rows_for_display(
        runtime.query_task_rows(conn, owner=None, state_scope=scope, limit=limit)
    )
    clear_screen()
    print(f"All tasks (scope={scope}, count={len(rows)})\n")

    if not rows:
        print("No tasks found.")
        pause()
        return

    table_rows = [
        [
            str(index),
            short_id(row["task_id"]),
            row["owner"],
            row["state"],
            runtime.body_preview(render_text(row["body"]), 48),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    headers = ["no", "task_id", "owner", "status", "body_preview"]
    title_lines = [f"All tasks (scope={scope}, count={len(rows)})"]

    while rows:
        selected = interactive_table_selection(
            title_lines=title_lines,
            headers=headers,
            rows=table_rows,
            label="task",
            raw_rows=rows,
            id_key="task_id",
        )
        if selected.action != ACTION_SELECT or selected.index is None:
            break
        clear_screen()
        print("Task Detail")
        show_task_detail(conn, rows[selected.index]["task_id"])
        pause()


def view_tasks_by_member(conn: sqlite3.Connection, team_root: Path) -> None:
    clear_screen()
    print("View Tasks By Member")
    member = prompt_member(conn, team_root)
    scope = prompt_scope("Task scope", TASK_SCOPE_CHOICES, "open")
    limit = prompt_int("Limit", 50)

    rows = sort_task_rows_for_display(
        runtime.query_task_rows(conn, owner=member, state_scope=scope, limit=limit)
    )
    clear_screen()
    print(f"Tasks for {member} (scope={scope}, count={len(rows)})\n")
    table_rows = [
        [
            str(index),
            short_id(row["task_id"]),
            row["state"][:12],
            str(row["priority"]),
            row["updated_at"][:20],
            runtime.body_preview(render_text(row["body"]), 42),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    if not table_rows:
        print("No tasks found.")
        pause()
        return

    headers = ["no", "task_id", "state", "prio", "updated_at", "body"]
    title_lines = [f"Tasks for {member} (scope={scope}, count={len(rows)})"]

    while rows:
        selected = interactive_table_selection(
            title_lines=title_lines,
            headers=headers,
            rows=table_rows,
            label="task",
            raw_rows=rows,
            id_key="task_id",
        )
        if selected.action != ACTION_SELECT or selected.index is None:
            break
        clear_screen()
        print("Task Detail")
        show_task_detail(conn, rows[selected.index]["task_id"])
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

        if row["status"] == "unread" and row["receiver"] == "ceo":
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
        print(f"{key}: {render_text(row[key])}")
    print("body:")
    print(render_text(row["body"]))


def compose_reply_for_message_prompt(
    conn: sqlite3.Connection,
    receiver_default: str,
    subject_default: str,
    task_default: str | None,
) -> bool:
    receiver_raw = prompt_line("Reply receiver", receiver_default)
    try:
        receiver = runtime.normalize_identity(receiver_raw, "receiver")
    except ValueError as exc:
        print(exc)
        pause()
        return False

    subject = prompt_line("Reply subject", subject_default).strip()

    linked_task_raw = prompt_line("Linked task UUID (blank for none)", task_default or "")
    task_id: str | None
    if linked_task_raw:
        try:
            task_id = runtime.normalize_uuid(linked_task_raw, "task-id")
        except ValueError as exc:
            print(exc)
            pause()
            return False
    else:
        task_id = None

    try:
        body = prompt_multiline("Reply body")
    except ValueError as exc:
        print(exc)
        pause()
        return False

    reply_id = send_ceo_message(conn, receiver, subject, body, task_id)
    print("\nReply sent.")
    print(f"reply_id: {reply_id}")
    print("from: ceo")
    print(f"to: {receiver}")
    pause()
    return True


def compose_reply_panel(
    conn: sqlite3.Connection,
    original: sqlite3.Row,
    receiver: str,
    subject: str,
    task_id: str | None,
) -> bool:
    message_lines = build_message_detail_lines(original)
    draft_lines = [""]
    cursor_line = 0
    cursor_col = 0
    draft_top = 0
    message_top = 0
    status_line = ""

    with RawKeyboardSession() as fd:
        while True:
            term_size = shutil.get_terminal_size(fallback=(100, 24))
            total_lines = max(12, term_size.lines)
            separator = "-" * max(20, min(term_size.columns, 120))
            draft_height = max(4, min(10, total_lines // 3))
            message_height = max(4, total_lines - draft_height - 9)
            max_message_top = max(0, len(message_lines) - message_height)
            message_top = max(0, min(message_top, max_message_top))

            if cursor_line < draft_top:
                draft_top = cursor_line
            elif cursor_line >= draft_top + draft_height:
                draft_top = cursor_line - draft_height + 1
            max_draft_top = max(0, len(draft_lines) - draft_height)
            draft_top = max(0, min(draft_top, max_draft_top))

            clear_screen()
            print("Reply Draft (message above, draft below)")
            print(
                "F2 send | F1 cancel draft and return | Ctrl-S/Ctrl-Q also supported | PgUp/PgDn scroll message pane"
            )
            print()

            for index in range(message_top, min(len(message_lines), message_top + message_height)):
                print(message_lines[index])
            for _ in range(message_height - len(message_lines[message_top : message_top + message_height])):
                print()

            print(separator)
            print(f"to: {receiver} | subject: {subject} | task_id: {task_id or '-'}")

            for index in range(draft_top, min(len(draft_lines), draft_top + draft_height)):
                is_cursor = index == cursor_line
                prefix = "> " if is_cursor else "  "
                content = (
                    render_editor_line_with_cursor(draft_lines[index], cursor_col)
                    if is_cursor
                    else draft_lines[index]
                )
                print(f"{prefix}{content}")
            for _ in range(draft_height - len(draft_lines[draft_top : draft_top + draft_height])):
                print()

            print(status_line)
            status_line = ""

            key, payload = read_editor_key(fd)

            if key in {KEY_CTRL_Q, KEY_F1}:
                return False

            if key in {KEY_CTRL_S, KEY_F2}:
                body = "\n".join(draft_lines).strip()
                if not body:
                    status_line = "Draft body cannot be empty."
                    continue
                reply_id = send_ceo_message(conn, receiver, subject, body, task_id)
                clear_screen()
                print("Reply sent.")
                print(f"reply_id: {reply_id}")
                print("from: ceo")
                print(f"to: {receiver}")
                pause()
                return True

            if key == "char":
                line = draft_lines[cursor_line]
                draft_lines[cursor_line] = line[:cursor_col] + payload + line[cursor_col:]
                cursor_col += len(payload)
                continue

            if key == KEY_ENTER:
                line = draft_lines[cursor_line]
                left = line[:cursor_col]
                right = line[cursor_col:]
                draft_lines[cursor_line] = left
                draft_lines.insert(cursor_line + 1, right)
                cursor_line += 1
                cursor_col = 0
                continue

            if key == KEY_BACKSPACE:
                line = draft_lines[cursor_line]
                if cursor_col > 0:
                    draft_lines[cursor_line] = line[: cursor_col - 1] + line[cursor_col:]
                    cursor_col -= 1
                elif cursor_line > 0:
                    previous = draft_lines[cursor_line - 1]
                    cursor_col = len(previous)
                    draft_lines[cursor_line - 1] = previous + line
                    del draft_lines[cursor_line]
                    cursor_line -= 1
                continue

            if key == KEY_LEFT:
                if cursor_col > 0:
                    cursor_col -= 1
                elif cursor_line > 0:
                    cursor_line -= 1
                    cursor_col = len(draft_lines[cursor_line])
                continue

            if key == KEY_RIGHT:
                line_len = len(draft_lines[cursor_line])
                if cursor_col < line_len:
                    cursor_col += 1
                elif cursor_line < len(draft_lines) - 1:
                    cursor_line += 1
                    cursor_col = 0
                continue

            if key == KEY_UP:
                if cursor_line > 0:
                    cursor_line -= 1
                    cursor_col = min(cursor_col, len(draft_lines[cursor_line]))
                continue

            if key == KEY_DOWN:
                if cursor_line < len(draft_lines) - 1:
                    cursor_line += 1
                    cursor_col = min(cursor_col, len(draft_lines[cursor_line]))
                continue

            if key == KEY_PAGE_UP:
                message_top = max(0, message_top - message_height)
                continue

            if key == KEY_PAGE_DOWN:
                message_top = min(max_message_top, message_top + message_height)
                continue


def compose_reply_for_message(conn: sqlite3.Connection, original: sqlite3.Row) -> bool:
    try:
        receiver_default = runtime.normalize_identity(str(original["sender"]), "receiver")
    except ValueError as exc:
        print(exc)
        pause()
        return False

    subject_seed = (
        original["subject"].strip()
        if original["subject"]
        else f"message {str(original['message_id'])[:8]}"
    )
    subject_default = f"Re: {subject_seed}"
    task_default = str(original["task_id"]) if original["task_id"] else None

    if supports_interactive_navigation():
        return compose_reply_panel(
            conn=conn,
            original=original,
            receiver=receiver_default,
            subject=subject_default,
            task_id=task_default,
        )

    return compose_reply_for_message_prompt(
        conn=conn,
        receiver_default=receiver_default,
        subject_default=subject_default,
        task_default=task_default,
    )


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

        if not rows:
            clear_screen()
            print(f"Archived messages for {member} (count=0)\n")
            print("No archived messages found.")
            pause()
            return

        table_rows = [
            [
                str(index),
                short_id(row["message_id"]),
                row["receiver"],
                row["status"],
                runtime.body_preview(render_text(row["body"]), 48),
            ]
            for index, row in enumerate(rows, start=1)
        ]
        headers = ["no", "message_id", "owner", "status", "body_preview"]
        title_lines = [f"Archived messages for {member} (count={len(rows)})"]

        selected = interactive_table_selection(
            title_lines=title_lines,
            headers=headers,
            rows=table_rows,
            label="message",
            raw_rows=rows,
            id_key="message_id",
        )
        if selected.action != ACTION_SELECT or selected.index is None:
            break

        message_id = rows[selected.index]["message_id"]
        updated = unarchive_message_for_member(conn, member, message_id)
        clear_screen()
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

    if not rows:
        clear_screen()
        print(f"All messages (scope={scope}, count=0)\n")
        print("No messages found.")
        pause()
        return

    table_rows = [
        [
            str(index),
            short_id(row["message_id"]),
            row["sender"],
            row["receiver"],
            format_timestamp_human(row["created_at"]),
            row["status"],
            runtime.body_preview(render_text(row["body"]), 48),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    headers = ["no", "message_id", "from", "to", "timestamp", "status", "body_preview"]
    title_lines = [f"All messages (scope={scope}, count={len(rows)})"]

    while rows:
        selected = interactive_table_selection(
            title_lines=title_lines,
            headers=headers,
            rows=table_rows,
            label="message",
            raw_rows=rows,
            id_key="message_id",
        )
        if selected.action != ACTION_SELECT or selected.index is None:
            break
        message = read_message(conn, rows[selected.index]["message_id"])
        if message is None:
            clear_screen()
            print("Message not found.")
            pause()
            continue
        clear_screen()
        print("Message Detail")
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

    table_rows = [
        [
            str(index),
            short_id(row["message_id"]),
            row["receiver"],
            row["status"],
            runtime.body_preview(render_text(row["body"]), 48),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    if not table_rows:
        clear_screen()
        print(f"Messages for {member} (scope={scope}, count=0)\n")
        print("No messages found.")
        pause()
        return

    headers = ["no", "message_id", "owner", "status", "body_preview"]
    title_lines = [f"Messages for {member} (scope={scope}, count={len(rows)})"]

    while rows:
        selected = interactive_table_selection(
            title_lines=title_lines,
            headers=headers,
            rows=table_rows,
            label="message",
            raw_rows=rows,
            id_key="message_id",
        )
        if selected.action != ACTION_SELECT or selected.index is None:
            break
        message = read_message(conn, rows[selected.index]["message_id"])
        if message is None:
            clear_screen()
            print("Message not found.")
            pause()
            continue
        clear_screen()
        print("Message Detail")
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

    if not rows:
        clear_screen()
        print("Selectable messages addressed to ceo (all statuses):")
        print(" (none)")
        pause()
        return

    table_rows = [
        [
            str(index),
            short_id(row["message_id"]),
            row["sender"],
            row["receiver"],
            format_timestamp_human(row["created_at"]),
            row["status"],
            runtime.body_preview(render_text(row["body"]), 48),
        ]
        for index, row in enumerate(rows, start=1)
    ]
    headers = ["no", "message_id", "from", "to", "timestamp", "status", "body_preview"]
    title_lines = ["Selectable messages addressed to ceo (all statuses):"]

    selected = interactive_table_selection(
        title_lines=title_lines,
        headers=headers,
        rows=table_rows,
        label="message",
        raw_rows=rows,
        id_key="message_id",
    )
    if selected.action != ACTION_SELECT or selected.index is None:
        return

    message_id = rows[selected.index]["message_id"]
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
            WHERE message_id = ? AND receiver = 'ceo'
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


def build_task_detail_lines(row: sqlite3.Row) -> list[str]:
    body_lines = render_text(row["body"]).splitlines() or [""]
    lines = [
        f"task_id: {row['task_id']}",
        f"owner: {render_text(row['owner'])}",
        f"state: {render_text(row['state'])}",
        f"priority: {render_text(row['priority'])}",
        f"created_by: {render_text(row['created_by'])}",
        f"created_at: {render_text(row['created_at'])}",
        f"updated_at: {render_text(row['updated_at'])}",
        f"blocked_reason: {render_text(row['blocked_reason'])}",
        "body:",
    ]
    lines.extend(body_lines)
    return lines


def build_message_detail_lines(row: sqlite3.Row) -> list[str]:
    body_lines = render_text(row["body"]).splitlines() or [""]
    lines = [
        f"message_id: {row['message_id']}",
        f"sender: {render_text(row['sender'])}",
        f"receiver: {render_text(row['receiver'])}",
        f"status: {render_text(row['status'])}",
        f"created_at: {render_text(row['created_at'])}",
        f"read_at: {render_text(row['read_at'])}",
        f"archived_at: {render_text(row['archived_at'])}",
        f"task_id: {render_text(row['task_id'])}",
        f"subject: {render_text(row['subject'])}",
        "body:",
    ]
    lines.extend(body_lines)
    return lines


def query_tasks_created_from_message(
    conn: sqlite3.Connection,
    message_row: sqlite3.Row,
) -> list[sqlite3.Row]:
    # Trace related tasks via explicit message.task_id links and message_id references in task/message text.
    message_id = str(message_row["message_id"])
    message_like = f"%{message_id.lower()}%"
    clauses = [
        "lower(t.body) LIKE ?",
        """
        t.task_id IN (
            SELECT m.task_id
            FROM messages m
            WHERE m.task_id IS NOT NULL
              AND (
                  m.message_id = ?
                  OR lower(m.body) LIKE ?
                  OR lower(m.subject) LIKE ?
              )
        )
        """,
    ]
    params: list[object] = [message_like, message_id, message_like, message_like]

    linked_task_id = str(message_row["task_id"] or "").strip()
    if linked_task_id:
        clauses.append("t.task_id = ?")
        params.append(linked_task_id)

    where_clause = " OR ".join(clauses)
    return conn.execute(
        f"""
        SELECT DISTINCT t.task_id, t.owner, t.state, t.priority, t.body, t.created_at, t.updated_at
        FROM tasks t
        WHERE {where_clause}
        ORDER BY t.priority DESC, t.created_at ASC, t.task_id ASC
        """,
        params,
    ).fetchall()


def build_related_task_lines(rows: list[sqlite3.Row]) -> list[str]:
    lines = ["", "tasks_created_from_message:"]
    if not rows:
        lines.append("(none found)")
        return lines

    table_rows = [
        [
            str(row["task_id"]),
            render_text(row["owner"]),
            render_text(row["state"]),
            str(row["priority"]),
            runtime.body_preview(render_text(row["body"]), 56),
        ]
        for row in rows
    ]
    header_line, separator_line, row_lines = build_table_lines(
        headers=["task_id", "owner", "state", "prio", "body_preview"],
        rows=table_rows,
    )
    lines.append(header_line)
    lines.append(separator_line)
    lines.extend(row_lines)
    lines.append("Tip: hover task_id and press Enter to open task detail.")
    return lines


def build_message_detail_with_tasks(
    conn: sqlite3.Connection,
    message_row: sqlite3.Row,
) -> list[str]:
    lines = build_message_detail_lines(message_row)
    related_tasks = query_tasks_created_from_message(conn, message_row)
    lines.extend(build_related_task_lines(related_tasks))
    return lines


def cycle_choice(current: str, choices: tuple[str, ...]) -> str:
    if current not in choices:
        return choices[0]
    index = choices.index(current)
    return choices[(index + 1) % len(choices)]


def prompt_optional_identity_filter(
    label: str,
    current: str,
    field_name: str,
) -> str:
    while True:
        shown = current or "*"
        raw = input(f"{label} filter (Enter keep, '-' clear) [{shown}]: ").strip()
        if not raw:
            return current
        if raw == "-":
            return ""
        try:
            return runtime.normalize_identity(raw, field_name)
        except ValueError as exc:
            print(exc)


def prompt_optional_text_filter(label: str, current: str) -> str:
    shown = current or "*"
    raw = input(f"{label} text filter (Enter keep, '-' clear) [{shown}]: ").strip()
    if not raw:
        return current
    if raw == "-":
        return ""
    return raw


def format_filter_value(value: str) -> str:
    return value if value else "*"


def query_task_rows_for_screen(
    conn: sqlite3.Connection,
    owner: str,
    scope: str,
    text: str,
    limit: int,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[object] = []

    if owner:
        clauses.append("owner = ?")
        params.append(owner)

    if scope == "open":
        clauses.append("state IN ('todo', 'in_progress', 'blocked')")
    elif scope != "all":
        clauses.append("state = ?")
        params.append(scope)

    if text:
        like = f"%{text.lower()}%"
        clauses.append(
            """
            (
                lower(task_id) LIKE ?
                OR lower(owner) LIKE ?
                OR lower(state) LIKE ?
                OR lower(COALESCE(created_by, '')) LIKE ?
                OR lower(COALESCE(blocked_reason, '')) LIKE ?
                OR lower(body) LIKE ?
            )
            """
        )
        params.extend([like, like, like, like, like, like])

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT task_id, owner, state, body, priority, created_by, created_at, updated_at, blocked_reason
        FROM tasks
        {where_clause}
        ORDER BY priority DESC, created_at ASC, task_id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return sort_task_rows_for_display(rows)


def screen_menu(conn: sqlite3.Connection, team_root: Path, db_path: Path) -> ScreenResult:
    title_lines = [
        "Team CEO Console (Human-only)",
        f"team: {team_root}",
        f"db:   {db_path}",
    ]
    options = [
        "View tasks table",
        "View messages table",
        "View CEO inbox",
        "Respond to a message",
        "Send a message to a member",
        "Quit",
    ]
    selected = interactive_menu_selection(
        title_lines=title_lines,
        options=options,
        prompt="Use Up/Down arrows and Enter. Press b/f for history and q to quit.",
    )

    if selected.action == ACTION_BACK:
        return ScreenResult(ACTION_BACK)
    if selected.action == ACTION_FORWARD:
        return ScreenResult(ACTION_FORWARD)
    if selected.action == ACTION_CANCEL:
        return ScreenResult(ACTION_QUIT)
    if selected.index is None:
        return ScreenResult(ACTION_STAY)

    choice = selected.index
    if choice == 0:
        return ScreenResult(
            ACTION_OPEN,
            ScreenEntry(SCREEN_TASK_LIST, ("", "all", "", DEFAULT_TABLE_LIMIT)),
        )
    if choice == 1:
        return ScreenResult(
            ACTION_OPEN,
            ScreenEntry(SCREEN_MESSAGE_LIST, ("", "", "all", "", DEFAULT_TABLE_LIMIT)),
        )
    if choice == 2:
        return ScreenResult(
            ACTION_OPEN,
            ScreenEntry(SCREEN_MESSAGE_LIST, ("", "ceo", "inbox", "", DEFAULT_TABLE_LIMIT)),
        )
    if choice == 3:
        return ScreenResult(
            ACTION_OPEN,
            ScreenEntry(SCREEN_MESSAGE_LIST, ("", "ceo", "all", "", DEFAULT_TABLE_LIMIT)),
        )
    if choice == 4:
        send_message_to_member(conn, team_root)
        return ScreenResult(ACTION_STAY)
    return ScreenResult(ACTION_QUIT)


def screen_task_list(conn: sqlite3.Connection, screen: ScreenEntry) -> ScreenResult:
    if len(screen.params) >= 4:
        owner, scope, text, limit = (
            str(screen.params[0]),
            str(screen.params[1]),
            str(screen.params[2]),
            int(screen.params[3]),
        )
    else:
        owner_raw, scope, limit = screen.params
        owner = str(owner_raw) if owner_raw else ""
        text = ""
        scope = str(scope)
        limit = int(limit)

    selected_index = 0
    notice = ""

    hotkeys = {
        "/": ACTION_FILTER_TEXT,
        "o": ACTION_FILTER_OWNER,
        "s": ACTION_FILTER_SCOPE,
        "l": ACTION_FILTER_LIMIT,
        "c": ACTION_FILTER_CLEAR,
    }

    while True:
        rows = query_task_rows_for_screen(conn, owner=owner, scope=scope, text=text, limit=limit)
        title_lines = [
            f"Task table (count={len(rows)})",
            (
                "Filters: "
                f"owner={format_filter_value(owner)} | "
                f"scope={scope} | "
                f"text={format_filter_value(text)} | "
                f"limit={limit}"
            ),
        ]
        if notice:
            title_lines.append(f"Last action: {notice}")

        table_rows = [
            [
                str(index),
                short_id(row["task_id"]),
                row["owner"],
                row["state"],
                str(row["priority"]),
                runtime.body_preview(render_text(row["body"]), 48),
            ]
            for index, row in enumerate(rows, start=1)
        ]

        selection = interactive_table_selection(
            title_lines=title_lines,
            headers=["no", "task_id", "owner", "state", "prio", "body_preview"],
            rows=table_rows,
            label="task",
            raw_rows=rows,
            id_key="task_id",
            hotkeys=hotkeys,
            hotkey_help=(
                "Hotkeys: / text | o owner | s scope cycle | l limit | c clear filters"
            ),
            initial_index=selected_index,
        )
        if selection.index is not None:
            selected_index = selection.index

        if selection.action == ACTION_BACK:
            return ScreenResult(ACTION_BACK)
        if selection.action == ACTION_FORWARD:
            return ScreenResult(ACTION_FORWARD)
        if selection.action == ACTION_CANCEL:
            return ScreenResult(ACTION_CANCEL)
        if selection.action == ACTION_SELECT and selection.index is not None:
            task_id = str(rows[selection.index]["task_id"])
            return ScreenResult(ACTION_OPEN, ScreenEntry(SCREEN_TASK_DETAIL, (task_id,)))
        if selection.action == ACTION_FILTER_SCOPE:
            scope = cycle_choice(scope, TASK_SCOPE_CHOICES)
            notice = f"scope -> {scope}"
            continue
        if selection.action == ACTION_FILTER_OWNER:
            clear_screen()
            owner = prompt_optional_identity_filter("Owner", owner, "owner")
            notice = f"owner -> {format_filter_value(owner)}"
            continue
        if selection.action == ACTION_FILTER_TEXT:
            clear_screen()
            text = prompt_optional_text_filter("Task", text)
            notice = f"text -> {format_filter_value(text)}"
            continue
        if selection.action == ACTION_FILTER_LIMIT:
            clear_screen()
            limit = prompt_int("Limit", limit)
            notice = f"limit -> {limit}"
            continue
        if selection.action == ACTION_FILTER_CLEAR:
            owner = ""
            scope = "all"
            text = ""
            limit = DEFAULT_TABLE_LIMIT
            notice = "filters reset"
            continue

        notice = ""


def query_message_rows_for_screen(
    conn: sqlite3.Connection,
    sender: str,
    receiver: str,
    scope: str,
    text: str,
    limit: int,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[object] = []

    if sender:
        clauses.append("sender = ?")
        params.append(sender)
    if receiver:
        clauses.append("receiver = ?")
        params.append(receiver)

    if scope == "inbox":
        clauses.append("status IN ('unread', 'read')")
    elif scope != "all":
        clauses.append("status = ?")
        params.append(scope)

    if text:
        like = f"%{text.lower()}%"
        clauses.append(
            """
            (
                lower(message_id) LIKE ?
                OR lower(sender) LIKE ?
                OR lower(receiver) LIKE ?
                OR lower(subject) LIKE ?
                OR lower(body) LIKE ?
                OR lower(COALESCE(task_id, '')) LIKE ?
            )
            """
        )
        params.extend([like, like, like, like, like, like])

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    return conn.execute(
        f"""
        SELECT message_id, sender, receiver, subject, body, created_at, status, read_at, archived_at, task_id
        FROM messages
        {where_clause}
        ORDER BY receiver ASC, created_at DESC, message_id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()


def screen_message_list(conn: sqlite3.Connection, screen: ScreenEntry) -> ScreenResult:
    if len(screen.params) >= 5 and str(screen.params[0]) in {"all", "member"}:
        mode, member, scope, sender, limit = screen.params
        receiver = "" if str(mode) == "all" else str(member)
        text = ""
        sender = str(sender)
        scope = str(scope)
        limit = int(limit)
    else:
        sender, receiver, scope, text, limit = (
            str(screen.params[0]),
            str(screen.params[1]),
            str(screen.params[2]),
            str(screen.params[3]),
            int(screen.params[4]),
        )

    selected_index = 0
    notice = ""

    hotkeys = {
        "/": ACTION_FILTER_TEXT,
        "o": ACTION_FILTER_ORIGIN,
        "d": ACTION_FILTER_DESTINATION,
        "s": ACTION_FILTER_SCOPE,
        "l": ACTION_FILTER_LIMIT,
        "c": ACTION_FILTER_CLEAR,
        "a": ACTION_ARCHIVE_HOVERED,
        "u": ACTION_UNARCHIVE_HOVERED,
    }

    while True:
        rows = query_message_rows_for_screen(
            conn=conn,
            sender=sender,
            receiver=receiver,
            scope=scope,
            text=text,
            limit=limit,
        )
        title_lines = [
            f"Message table (count={len(rows)})",
            (
                "Filters: "
                f"from={format_filter_value(sender)} | "
                f"to={format_filter_value(receiver)} | "
                f"scope={scope} | "
                f"text={format_filter_value(text)} | "
                f"limit={limit}"
            ),
        ]
        if notice:
            title_lines.append(f"Last action: {notice}")

        table_rows = [
            [
                str(index),
                short_id(row["message_id"]),
                row["sender"],
                row["receiver"],
                format_timestamp_human(row["created_at"]),
                row["status"],
                runtime.body_preview(render_text(row["body"]), 48),
            ]
            for index, row in enumerate(rows, start=1)
        ]

        selection = interactive_table_selection(
            title_lines=title_lines,
            headers=["no", "message_id", "from", "to", "timestamp", "status", "body_preview"],
            rows=table_rows,
            label="message",
            raw_rows=rows,
            id_key="message_id",
            hotkeys=hotkeys,
            hotkey_help=(
                "Hotkeys: / text | o from | d to | s scope cycle | l limit | c clear | a archive hovered | u unarchive hovered"
            ),
            initial_index=selected_index,
        )
        if selection.index is not None:
            selected_index = selection.index

        if selection.action == ACTION_BACK:
            return ScreenResult(ACTION_BACK)
        if selection.action == ACTION_FORWARD:
            return ScreenResult(ACTION_FORWARD)
        if selection.action == ACTION_CANCEL:
            return ScreenResult(ACTION_CANCEL)
        if selection.action == ACTION_SELECT and selection.index is not None:
            message_id = str(rows[selection.index]["message_id"])
            return ScreenResult(ACTION_OPEN, ScreenEntry(SCREEN_MESSAGE_DETAIL, (message_id,)))
        if selection.action == ACTION_FILTER_SCOPE:
            scope = cycle_choice(scope, MESSAGE_SCOPE_CYCLE)
            notice = f"scope -> {scope}"
            continue
        if selection.action == ACTION_FILTER_ORIGIN:
            clear_screen()
            sender = prompt_optional_identity_filter("From", sender, "sender")
            notice = f"from -> {format_filter_value(sender)}"
            continue
        if selection.action == ACTION_FILTER_DESTINATION:
            clear_screen()
            receiver = prompt_optional_identity_filter("To", receiver, "receiver")
            notice = f"to -> {format_filter_value(receiver)}"
            continue
        if selection.action == ACTION_FILTER_TEXT:
            clear_screen()
            text = prompt_optional_text_filter("Message", text)
            notice = f"text -> {format_filter_value(text)}"
            continue
        if selection.action == ACTION_FILTER_LIMIT:
            clear_screen()
            limit = prompt_int("Limit", limit)
            notice = f"limit -> {limit}"
            continue
        if selection.action == ACTION_FILTER_CLEAR:
            sender = ""
            receiver = ""
            scope = "all"
            text = ""
            limit = DEFAULT_TABLE_LIMIT
            notice = "filters reset"
            continue
        if selection.action in {ACTION_ARCHIVE_HOVERED, ACTION_UNARCHIVE_HOVERED}:
            if selection.index is None or not rows:
                notice = "No hovered row."
                continue
            row = rows[selection.index]
            message_id = str(row["message_id"])
            owner = str(row["receiver"])
            is_archived = str(row["status"]) == "archived"

            if selection.action == ACTION_ARCHIVE_HOVERED:
                if is_archived:
                    notice = "Hovered message is already archived."
                    continue
                updated = archive_message_for_member(conn, owner, message_id)
                notice = (
                    f"archived {short_id(message_id)}"
                    if updated is not None
                    else "Message not found."
                )
                continue

            if not is_archived:
                notice = "Hovered message is not archived."
                continue
            updated = unarchive_message_for_member(conn, owner, message_id)
            notice = (
                f"unarchived {short_id(message_id)}"
                if updated is not None
                else "Message not found."
            )
            continue

        notice = ""


def screen_task_detail(conn: sqlite3.Connection, screen: ScreenEntry) -> ScreenResult:
    task_id = str(screen.params[0])
    row = conn.execute(
        """
        SELECT task_id, owner, state, body, priority, created_by, created_at, updated_at, blocked_reason
        FROM tasks
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchone()
    if row is None:
        clear_screen()
        print("Task not found.")
        pause()
        return ScreenResult(ACTION_CANCEL)

    result = interactive_readonly_view(
        conn=conn,
        title_lines=["Task Detail"],
        content_lines=build_task_detail_lines(row),
        can_reply=False,
    )
    if result.action == ACTION_SELECT and result.screen is not None:
        return ScreenResult(ACTION_OPEN, result.screen)
    if result.action in {ACTION_BACK, ACTION_FORWARD, ACTION_CANCEL}:
        return ScreenResult(result.action)
    return ScreenResult(ACTION_STAY)


def screen_message_detail(conn: sqlite3.Connection, screen: ScreenEntry) -> ScreenResult:
    message_id = str(screen.params[0])
    row = read_message(conn, message_id)
    if row is None:
        clear_screen()
        print("Message not found.")
        pause()
        return ScreenResult(ACTION_CANCEL)

    result = interactive_readonly_view(
        conn=conn,
        title_lines=["Message Detail"],
        content_lines=build_message_detail_with_tasks(conn, row),
        can_reply=row["receiver"] == "ceo",
    )
    if result.action == "reply":
        compose_reply_for_message(conn, row)
        return ScreenResult(ACTION_STAY)
    if result.action == ACTION_SELECT and result.screen is not None:
        return ScreenResult(ACTION_OPEN, result.screen)
    if result.action == ACTION_CANCEL:
        if row["status"] != "archived" and prompt_yes_no("\nArchive this message?", default=False):
            updated = archive_message_for_member(conn, row["receiver"], row["message_id"])
            clear_screen()
            if updated is None:
                print("Message not found.")
            else:
                print(f"Message archived: {updated['message_id']}")
            pause()
        return ScreenResult(ACTION_CANCEL)
    if result.action in {ACTION_BACK, ACTION_FORWARD}:
        return ScreenResult(result.action)
    return ScreenResult(ACTION_STAY)


def run_screen(
    conn: sqlite3.Connection,
    team_root: Path,
    db_path: Path,
    screen: ScreenEntry,
) -> ScreenResult:
    if screen.kind == SCREEN_MENU:
        return screen_menu(conn, team_root, db_path)
    if screen.kind == SCREEN_TASK_LIST:
        return screen_task_list(conn, screen)
    if screen.kind == SCREEN_MESSAGE_LIST:
        return screen_message_list(conn, screen)
    if screen.kind == SCREEN_TASK_DETAIL:
        return screen_task_detail(conn, screen)
    if screen.kind == SCREEN_MESSAGE_DETAIL:
        return screen_message_detail(conn, screen)

    clear_screen()
    print(f"Unknown screen kind: {screen.kind}")
    pause()
    return ScreenResult(ACTION_CANCEL)


def run_tui(conn: sqlite3.Connection, team_root: Path, db_path: Path) -> int:
    history = ScreenHistory()
    current = ScreenEntry(SCREEN_MENU)
    history.visit(current)

    while True:
        outcome = run_screen(conn, team_root, db_path, current)

        if outcome.action == ACTION_QUIT:
            clear_screen()
            return 0

        if outcome.action == ACTION_OPEN and outcome.screen is not None:
            current = outcome.screen
            history.visit(current)
            continue

        if outcome.action in {ACTION_BACK, ACTION_CANCEL}:
            target = history.back()
            if target is not None:
                current = target
                continue
            if current.kind == SCREEN_MENU:
                clear_screen()
                return 0
            current = ScreenEntry(SCREEN_MENU)
            history.visit(current)
            continue

        if outcome.action == ACTION_FORWARD:
            target = history.forward()
            if target is not None:
                current = target
            continue

        if outcome.action == ACTION_STAY:
            continue


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
