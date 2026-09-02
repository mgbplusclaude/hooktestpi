"""Terminal rendering helpers.

Replaces HookTest's ``prettytable==0.7.2`` and ``ansicolors==1.0.2``
dependencies, neither of which installs cleanly on modern Python. The
table output is deliberately byte-compatible in spirit with the tables
HookTest printed (box-drawn with ``+``/``-``/``|``, horizontal rules
between every row) so existing log scrapers keep working.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata

__all__ = ["Table", "white", "magenta", "green", "red", "yellow", "bold", "supports_color"]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_CODES = {
    "black": 30, "red": 31, "green": 32, "yellow": 33,
    "blue": 34, "magenta": 35, "cyan": 36, "white": 37,
}


def supports_color(stream=None) -> bool:
    """Return True when it is safe to emit ANSI escapes on *stream*."""
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def _colorize(name: str):
    code = _CODES[name]

    def wrap(text, *, force: bool | None = None) -> str:
        text = str(text)
        use = supports_color() if force is None else force
        if not use:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    wrap.__name__ = name
    return wrap


white = _colorize("white")
magenta = _colorize("magenta")
green = _colorize("green")
red = _colorize("red")
yellow = _colorize("yellow")


def bold(text, *, force: bool | None = None) -> str:
    text = str(text)
    use = supports_color() if force is None else force
    return f"\x1b[1m{text}\x1b[0m" if use else text


def _display_width(text: str) -> int:
    """Width of *text* in terminal cells, ignoring ANSI escapes.

    Greek and Latin text in these corpora is narrow, but identifiers may
    carry combining accents (NFD Greek is common in TEI), which occupy no
    cell of their own.
    """
    plain = _ANSI_RE.sub("", text)
    width = 0
    for char in plain:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def _pad(text: str, width: int, align: str) -> str:
    padding = width - _display_width(text)
    if padding <= 0:
        return text
    if align == "l":
        return text + " " * padding
    if align == "r":
        return " " * padding + text
    left = padding // 2
    return " " * left + text + " " * (padding - left)


class Table:
    """A minimal box-drawing table.

    :param headers: column headers
    :param align: per-column alignment, one of ``l``, ``c``, ``r``;
        a single string applies to every column.
    """

    def __init__(self, headers, align: str = "c"):
        self.headers = [str(h) for h in headers]
        self.rows: list[list[str]] = []
        if len(align) == len(self.headers):
            self.align = list(align)
        else:
            self.align = [align[0]] * len(self.headers)

    def add_row(self, row) -> None:
        if len(row) != len(self.headers):
            raise ValueError(
                f"row has {len(row)} cells, expected {len(self.headers)}"
            )
        self.rows.append([str(cell) for cell in row])

    def _widths(self) -> list[int]:
        widths = [_display_width(h) for h in self.headers]
        for row in self.rows:
            for i, cell in enumerate(row):
                for line in cell.split("\n"):
                    widths[i] = max(widths[i], _display_width(line))
        return widths

    def _rule(self, widths) -> str:
        return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def _render_row(self, cells, widths) -> str:
        # A cell may span several lines; the row is as tall as its tallest cell.
        columns = [cell.split("\n") for cell in cells]
        height = max(len(c) for c in columns)
        out = []
        for line_no in range(height):
            parts = []
            for i, lines in enumerate(columns):
                text = lines[line_no] if line_no < len(lines) else ""
                parts.append(" " + _pad(text, widths[i], self.align[i]) + " ")
            out.append("|" + "|".join(parts) + "|")
        return "\n".join(out)

    def __str__(self) -> str:
        widths = self._widths()
        rule = self._rule(widths)
        out = [rule, self._render_row(self.headers, widths), rule]
        for row in self.rows:
            out.append(self._render_row(row, widths))
            out.append(rule)
        return "\n".join(out)
