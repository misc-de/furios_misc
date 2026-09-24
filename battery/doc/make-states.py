#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Draws the chart of states for the README.

With GTK's own symbolic renderer and the same colours `battctl` hands the
widget in the bar - not painted by hand. What is seen here is what phosh puts
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


def icon(name, power, filling):
    """The icon as GTK draws it with these colours: the power colour on
    the frame (and the bolt, which Adwaita draws in the same path), the
    filling colour on the level inside - what the widget in the bar does.
    """
    info = Gtk.IconTheme.get_default().lookup_icon(
        name, ICON_PX, Gtk.IconLookupFlags.FORCE_SYMBOLIC)
    inside = rgba(b.COLORS.get(filling, FG))
    front = rgba(b.COLORS.get(power, FG))
    pixbuf, _was_symbolic = info.load_symbolic(front, inside, inside, inside)
    return pixbuf


# (heading, [(icon name, frame colour, filling colour, label)])
#
# Adwaita's discharge icons above 20 % are one path, so the more urgent of
# the two colours takes the whole icon there - which is what the daemon
# decides as well.
D = b.DEFAULTS
CHART = [
    ("Charging - frame and bolt say how fast", [
        ("battery-level-80-charging-symbolic", "green", None,
         "from %g W" % D["charge_green_w"]),
        ("battery-level-80-charging-symbolic", "amber", None,
         "%g-%g W" % (D["charge_amber_w"], D["charge_green_w"])),
        ("battery-level-80-charging-symbolic", "red", None,
         "below %g W" % D["charge_amber_w"]),
    ]),
    ("On battery - the frame says how much is drawn", [
        ("battery-level-80-symbolic", None, None,
         "below %g W" % D["drain_amber_w"]),
        ("battery-level-80-symbolic", "amber", "amber",
         "%g-%g W" % (D["drain_amber_w"], D["drain_red_w"])),
        ("battery-level-80-symbolic", "red", "red",
         "from %g W" % D["drain_red_w"]),
    ]),
    ("Filling - the charge level, in both cases", [
        ("battery-level-80-symbolic", None, None, "above 60 %"),
        ("battery-level-40-symbolic", "amber", "amber", "15-60 %"),
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
