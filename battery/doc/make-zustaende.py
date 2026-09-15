#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Zeichnet die Zustandstafel fuer das README.

Mit GTKs eigenem Symbol-Renderer und denselben vier Farben, die `battctl`
in die Themes schreibt - nicht nachgemalt. Was hier zu sehen ist, ist
dasselbe, was phosh in die Leiste zeichnet, nur groesser.

    python3 doc/make-zustaende.py [ziel.png]
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
FG = "#ffffff"          # die Leistenfarbe: was "schlicht" bedeutet
GRUND = (0.08, 0.08, 0.09)
SYM = 56
SPALTE, ZEILE = 150, 132


def rgba(farbe):
    wert = Gdk.RGBA()
    wert.parse(farbe)
    return wert


def symbol(name, huelle, fuellung):
    """Das Symbol, wie GTK es mit diesen beiden Farben zeichnet."""
    info = Gtk.IconTheme.get_default().lookup_icon(
        name, SYM, Gtk.IconLookupFlags.FORCE_SYMBOLIC)
    vorn = rgba(b.COLORS.get(huelle, FG))
    innen = rgba(b.COLORS.get(fuellung, FG))
    pixbuf, _war_symbolisch = info.load_symbolic(vorn, innen, innen, innen)
    return pixbuf


# (Ueberschrift, [(Symbolname, Huelle, Fuellung, Beschriftung)])
TAFEL = [
    ("Laden - die Huelle sagt, wie schnell", [
        ("battery-level-80-charging-symbolic", "green", None, "ab 7 W"),
        ("battery-level-80-charging-symbolic", "amber", None, "3-7 W"),
        ("battery-level-80-charging-symbolic", "red", None, "unter 3 W"),
    ]),
    ("Akkubetrieb - ein Pfad, also eine Farbe", [
        ("battery-level-80-symbolic", None, None, "unter 2 W"),
        ("battery-level-80-symbolic", "amber", "amber", "2-4 W"),
        ("battery-level-80-symbolic", "red", "red", "ab 4 W"),
    ]),
    ("Ladestand - die Fuellung sagt, wie voll", [
        ("battery-level-80-charging-symbolic", "green", None, "ueber 60 %"),
        ("battery-level-40-charging-symbolic", "green", "amber", "15-60 %"),
        ("battery-level-10-charging-symbolic", "green", "red", "unter 15 %"),
    ]),
]


def zeichne(ziel):
    breite = SPALTE * 3 + 40
    hoehe = len(TAFEL) * (ZEILE + 34) + 20
    flaeche = cairo.ImageSurface(cairo.FORMAT_ARGB32, breite, hoehe)
    ctx = cairo.Context(flaeche)
    ctx.set_source_rgb(*GRUND)
    ctx.paint()

    y = 30
    for titel, zellen in TAFEL:
        ctx.select_font_face("sans", cairo.FONT_SLANT_NORMAL,
                             cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(15)
        ctx.set_source_rgb(0.62, 0.62, 0.66)
        ctx.move_to(20, y)
        ctx.show_text(titel)
        y += 22

        for i, (name, huelle, fuellung, text) in enumerate(zellen):
            x = 20 + i * SPALTE
            pixbuf = symbol(name, huelle, fuellung)
            Gdk.cairo_set_source_pixbuf(
                ctx, pixbuf,
                x + (SPALTE - pixbuf.get_width()) / 2, y + 8)
            ctx.paint()
            ctx.select_font_face("sans", cairo.FONT_SLANT_NORMAL,
                                 cairo.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(14)
            ctx.set_source_rgb(0.86, 0.86, 0.88)
            aus = ctx.text_extents(text)
            ctx.move_to(x + (SPALTE - aus.width) / 2, y + SYM + 32)
            ctx.show_text(text)
        y += ZEILE + 12

    flaeche.write_to_png(ziel)
    return ziel


if __name__ == "__main__":
    ziel = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HIER,
                                                              "zustaende.png")
    print(zeichne(ziel))
