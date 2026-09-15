#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Draws the chart of states for the README.

With GTK's own symbolic renderer and the same four colours `battctl` writes
into the themes - not painted by hand. What is seen here is what phosh puts
in the bar, only larger.

    python3 doc/make-states.py [target.png]
"""
import importlib.machinery
import importlib.util
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402
import cairo  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)


def battctl():
    lader = importlib.machinery.SourceFileLoader(
        "battctl", os.path.join(WURZEL, "battctl"))
    spec = importlib.util.spec_from_loader("battctl", lader)
    modul = importlib.util.module_from_spec(spec)
    lader.exec_module(modul)
    return modul


b = battctl()
FG = "#ffffff"          # the colour of the bar: what "plain" means
GROUND = (0.08, 0.08, 0.09)
ICON_PX = 56
COLUMN, ROW = 150, 132


def rgba(colour):
    value = Gdk.RGBA()
    value.parse(colour)
    return value


def icon(name, shell, filling):
    """The icon as GTK draws it with these two colours."""
    info = Gtk.IconTheme.get_default().lookup_icon(
        name, ICON_PX, Gtk.IconLookupFlags.FORCE_SYMBOLIC)
    front = rgba(b.COLORS.get(shell, FG))
    inside = rgba(b.COLORS.get(filling, FG))
    pixbuf, _was_symbolic = info.load_symbolic(front, inside, inside, inside)
    return pixbuf


# (heading, [(icon name, frame colour, filling colour, label)])
#
# The discharge icons come from ~/.local/share/icons, where battctl has
# written them - GTK searches there first, and only there do they have a
# filling area of their own. Without them the middle row shows one colour
# instead of two, and the chart thereby tells the truth about the phone it
# was drawn on.
CHART = [
    ("Charging - the frame says how fast", [
        ("battery-level-80-charging-symbolic", "green", None, "from 7 W"),
        ("battery-level-80-charging-symbolic", "amber", None, "3-7 W"),
        ("battery-level-80-charging-symbolic", "red", None, "below 3 W"),
    ]),
    ("On battery - the frame says how much is drawn", [
        ("battery-level-80-symbolic", None, None, "below 2 W"),
        ("battery-level-80-symbolic", "amber", None, "2-4 W"),
        ("battery-level-80-symbolic", "red", None, "from 4 W"),
    ]),
    ("Filling - the charge level, in both cases", [
        ("battery-level-80-symbolic", None, None, "above 60 %"),
        ("battery-level-40-symbolic", None, "amber", "15-60 %"),
        ("battery-level-10-symbolic", "red", "red", "below 15 %"),
    ]),
]


def draw(target):
    width = COLUMN * 3 + 40
    height = len(CHART) * (ROW + 34) + 20
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*GROUND)
    ctx.paint()

    y = 30
    for title, cells in CHART:
        ctx.select_font_face("sans", cairo.FONT_SLANT_NORMAL,
                             cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(15)
        ctx.set_source_rgb(0.62, 0.62, 0.66)
        ctx.move_to(20, y)
        ctx.show_text(title)
        y += 22

        for i, (name, shell, filling, text) in enumerate(cells):
            x = 20 + i * COLUMN
            pixbuf = icon(name, shell, filling)
            Gdk.cairo_set_source_pixbuf(
                ctx, pixbuf,
                x + (COLUMN - pixbuf.get_width()) / 2, y + 8)
            ctx.paint()
            ctx.select_font_face("sans", cairo.FONT_SLANT_NORMAL,
                                 cairo.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(14)
            ctx.set_source_rgb(0.86, 0.86, 0.88)
            out = ctx.text_extents(text)
            ctx.move_to(x + (COLUMN - out.width) / 2, y + ICON_PX + 32)
            ctx.show_text(text)
        y += ROW + 12

    surface.write_to_png(target)
    return target


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HIER,
                                                              "states.png")
    print(draw(target))
