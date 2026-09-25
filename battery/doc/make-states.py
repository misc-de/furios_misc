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
    the frame, the filling colour on the level inside - what the widget in
    the bar does. On a charging icon the power colour goes on the bolt
    instead (see bolt_only).
    """
    info = Gtk.IconTheme.get_default().lookup_icon(
        name, ICON_PX, Gtk.IconLookupFlags.FORCE_SYMBOLIC)
    inside = rgba(b.COLORS.get(filling, FG))
    if power and "-charging" in name:
        return bolt_only(info, inside, b.COLORS[power])
    front = rgba(b.COLORS.get(power, FG))
    pixbuf, _was_symbolic = info.load_symbolic(front, inside, inside, inside)
    return pixbuf


# The plugin's bolt_region, in the icon's 16 units: the outline through the
# gaps between frame, bolt and level (phosh-battery-time/battery-time.c).
BOLT = ((12.9, 7.0), (16.5, 7.0), (16.5, 16.5), (10.5, 16.5),
        (10.5, 13.6), (9.0, 13.6), (9.0, 10.9))


def bolt_only(info, inside, colour):
    """Frame plain, bolt in `colour`: the icon drawn as it is, and inside
    the bolt's region its own coverage used as the mask for the colour -
    the same compositing the widget does in paint_the_bolt."""
    plain, _ = info.load_symbolic(rgba(FG), inside, inside, inside)
    w, h = plain.get_width(), plain.get_height()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    unit = w / 16.0

    def region():
        ctx.move_to(BOLT[0][0] * unit, BOLT[0][1] * unit)
        for x, y in BOLT[1:]:
            ctx.line_to(x * unit, y * unit)
        ctx.close_path()

    ctx.save()
    ctx.rectangle(0, 0, w, h)
    region()
    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    ctx.clip()
    Gdk.cairo_set_source_pixbuf(ctx, plain, 0, 0)
    ctx.paint()
    ctx.restore()

    mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    mctx = cairo.Context(mask)
    Gdk.cairo_set_source_pixbuf(mctx, plain, 0, 0)
    mctx.paint()
    region()
    ctx.clip()
    ctx.set_source_rgba(*(lambda c: (c.red, c.green, c.blue, c.alpha))(
        rgba(colour)))
    ctx.mask_surface(mask, 0, 0)
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)


# (heading, [(icon name, frame colour, filling colour, label)])
#
# Adwaita's discharge icons above 20 % are one path, so the more urgent of
# the two colours takes the whole icon there - which is what the daemon
# decides as well.
D = b.DEFAULTS
CHART = [
    ("Charging - the bolt says how fast", [
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
        ("battery-level-80-symbolic", None, None,
         "above %g %%" % D["level_amber_pct"]),
        ("battery-level-40-symbolic", "amber", "amber",
         "%g-%g %%" % (D["level_red_pct"], D["level_amber_pct"])),
        ("battery-level-10-symbolic", "red", "red",
         "below %g %%" % D["level_red_pct"]),
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
