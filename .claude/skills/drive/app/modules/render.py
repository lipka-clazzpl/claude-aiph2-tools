"""Render a tmux pane to a PNG.

Captures the pane buffer (with ANSI escape sequences) via `tmux capture-pane -e`,
parses it through pyte to a structured screen buffer, then rasterizes each cell
via PIL. Works on detached sessions and is independent of any terminal emulator.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Tuple

import pyte
from PIL import Image, ImageDraw, ImageFont

from modules.errors import TmuxCommandError


# VS Code Dark+ ANSI palette. fg/bg defaults match the editor's terminal.
PALETTE: dict[str, Tuple[int, int, int]] = {
    "default_fg": (0xCC, 0xCC, 0xCC),
    "default_bg": (0x1E, 0x1E, 0x1E),
    "black":          (0x00, 0x00, 0x00),
    "red":            (0xCD, 0x31, 0x31),
    "green":          (0x0D, 0xBC, 0x79),
    "brown":          (0xE5, 0xE5, 0x10),  # pyte calls yellow "brown"
    "yellow":         (0xE5, 0xE5, 0x10),
    "blue":           (0x24, 0x72, 0xC8),
    "magenta":        (0xBC, 0x3F, 0xBC),
    "cyan":           (0x11, 0xA8, 0xCD),
    "white":          (0xE5, 0xE5, 0xE5),
    "brightblack":    (0x66, 0x66, 0x66),
    "brightred":      (0xF1, 0x4C, 0x4C),
    "brightgreen":    (0x23, 0xD1, 0x8B),
    "brightbrown":    (0xF5, 0xF5, 0x43),
    "brightyellow":   (0xF5, 0xF5, 0x43),
    "brightblue":     (0x3B, 0x8E, 0xEA),
    "brightmagenta":  (0xD6, 0x70, 0xD6),
    "brightcyan":     (0x29, 0xB8, 0xDB),
    "brightwhite":    (0xE5, 0xE5, 0xE5),
}

# Standard xterm 256-color cube + grayscale. Generated lazily.
_XTERM_256: list[Tuple[int, int, int]] | None = None


def _xterm_256() -> list[Tuple[int, int, int]]:
    global _XTERM_256
    if _XTERM_256 is not None:
        return _XTERM_256
    base16 = [
        PALETTE["black"], PALETTE["red"], PALETTE["green"], PALETTE["yellow"],
        PALETTE["blue"], PALETTE["magenta"], PALETTE["cyan"], PALETTE["white"],
        PALETTE["brightblack"], PALETTE["brightred"], PALETTE["brightgreen"],
        PALETTE["brightyellow"], PALETTE["brightblue"], PALETTE["brightmagenta"],
        PALETTE["brightcyan"], PALETTE["brightwhite"],
    ]
    cube = [0, 95, 135, 175, 215, 255]
    rgb_cube = [(cube[r], cube[g], cube[b])
                for r in range(6) for g in range(6) for b in range(6)]
    grayscale = [(8 + i * 10, 8 + i * 10, 8 + i * 10) for i in range(24)]
    _XTERM_256 = base16 + rgb_cube + grayscale
    return _XTERM_256


def _resolve_color(name: str, default: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if name == "default":
        return default
    if name in PALETTE:
        return PALETTE[name]
    # 6-digit hex (truecolor or 256-color resolved by pyte)
    if len(name) == 6:
        try:
            return (int(name[0:2], 16), int(name[2:4], 16), int(name[4:6], 16))
        except ValueError:
            return default
    # Pyte sometimes hands us "<int>" for 256-color indices it didn't resolve.
    if name.isdigit():
        idx = int(name)
        if 0 <= idx < 256:
            return _xterm_256()[idx]
    return default


# Menlo ships with Regular/Bold/Italic/BoldItalic in a single TTC.
_MENLO_TTC = "/System/Library/Fonts/Menlo.ttc"
_FONT_CACHE: dict[Tuple[bool, bool, int], ImageFont.FreeTypeFont] = {}


def _font(bold: bool, italic: bool, size: int) -> ImageFont.FreeTypeFont:
    key = (bold, italic, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    index = (2 if italic else 0) + (1 if bold else 0)  # 0=Reg 1=Bold 2=It 3=BoldIt
    try:
        font = ImageFont.truetype(_MENLO_TTC, size, index=index)
    except OSError:
        font = ImageFont.truetype(_MENLO_TTC, size, index=0)
    _FONT_CACHE[key] = font
    return font


def _capture_pane(session: str, pane: int = 0) -> bytes:
    target = f"{session}:.{pane}"
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", target, "-p", "-e"],
        capture_output=True, timeout=5,
    )
    if result.returncode != 0:
        raise TmuxCommandError(
            cmd=["capture-pane", "-t", target],
            stderr=result.stderr.decode(errors="replace"),
        )
    return result.stdout


def _pane_dims(session: str, pane: int = 0) -> Tuple[int, int]:
    target = f"{session}:.{pane}"
    result = subprocess.run(
        ["tmux", "display", "-t", target, "-p", "#{pane_width} #{pane_height}"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise TmuxCommandError(
            cmd=["display", "-t", target],
            stderr=result.stderr.strip(),
        )
    w, h = result.stdout.strip().split()
    return int(w), int(h)


def render_pane(
    session: str,
    output_path: str,
    pane: int = 0,
    font_size: int = 14,
) -> str:
    """Render a tmux pane to a PNG at output_path. Returns the path."""
    cols, rows = _pane_dims(session, pane)
    raw = _capture_pane(session, pane)

    # tmux capture-pane emits LF line breaks but pyte's LF only moves the cursor
    # down — to also return to col 0 we need CR. Inject one before each LF that
    # isn't already preceded by one.
    raw = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    screen = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(screen)
    stream.feed(raw)

    # Cell metrics from the regular font.
    reg = _font(False, False, font_size)
    # getlength on a single 'M' is more reliable than a multi-char average for
    # monospace fonts — Menlo is strict-monospace so all glyphs share the width.
    cell_w = max(1, int(round(reg.getlength("M"))))
    ascent, descent = reg.getmetrics()
    cell_h = ascent + descent

    img_w = cell_w * cols
    img_h = cell_h * rows
    img = Image.new("RGB", (img_w, img_h), color=PALETTE["default_bg"])
    draw = ImageDraw.Draw(img)

    default_fg = PALETTE["default_fg"]
    default_bg = PALETTE["default_bg"]

    for y in range(rows):
        line = screen.buffer[y]
        for x in range(cols):
            ch = line[x]

            fg = _resolve_color(ch.fg, default_fg)
            bg = _resolve_color(ch.bg, default_bg)
            if ch.reverse:
                fg, bg = bg, fg
            if ch.bold and ch.fg == "default":
                # bold without explicit color → brighten in many terminals
                fg = PALETTE["brightwhite"]

            px = x * cell_w
            py = y * cell_h

            if bg != default_bg:
                draw.rectangle([px, py, px + cell_w, py + cell_h], fill=bg)

            if ch.data and ch.data != " ":
                font = _font(ch.bold, ch.italics, font_size)
                draw.text((px, py), ch.data, font=font, fill=fg)

            if ch.underscore:
                yu = py + cell_h - max(1, descent // 2)
                draw.line([(px, yu), (px + cell_w, yu)], fill=fg, width=1)
            if ch.strikethrough:
                ys = py + cell_h // 2
                draw.line([(px, ys), (px + cell_w, ys)], fill=fg, width=1)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG", optimize=True)
    return output_path
