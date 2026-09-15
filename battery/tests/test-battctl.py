#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Everything in battctl that can be decided without a battery.

The measurement itself is a directory of files here, which is what
/sys/class/power_supply/battery is on the phone as well; the gsettings key is
a file too. So the parts that are hard to get right - the hysteresis, the
dwell time, which theme is ours and which is somebody's own - are tested
against inputs a real charge would take hours to produce.

What is NOT in here, deliberately: that phosh actually turns green. That is a
screenshot, and it lives in FINDINGS.md.
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load():
    loader = importlib.machinery.SourceFileLoader("battctl",
                                                  os.path.join(ROOT, "battctl"))
    spec = importlib.util.spec_from_loader("battctl", loader)
    modul = importlib.util.module_from_spec(spec)
    loader.exec_module(modul)
    return modul


b = load()


class Basis(unittest.TestCase):
    """A temporary phone: a battery directory, a themes directory, a config."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sysfs = os.path.join(self.tmp, "battery")
        self.themes = os.path.join(self.tmp, "themes")
        self.setting = os.path.join(self.tmp, "gtk-theme")
        os.makedirs(self.sysfs)
        os.makedirs(self.themes)
        self.alt = (b.SYSFS, b.CONFIG, b.THEMES, list(b.THEME_DIRS))
        self.alter_pfad = os.environ["PATH"]
        b.SYSFS = self.sysfs
        b.CONFIG = os.path.join(self.tmp, "config.json")
        b.THEMES = self.themes
        b.THEME_DIRS[:] = [self.themes]
        self.set_theme("base")
        os.environ["FURIOS_BATTERY_SETTING_FILE"] = self.setting
        # No icon name unless a test says one: otherwise every run would
        # depend on what this phone's UPower is saying at the time.
        os.environ["FURIOS_BATTERY_ICON"] = ""

    def tearDown(self):
        b.SYSFS, b.CONFIG, b.THEMES = self.alt[:3]
        b.THEME_DIRS[:] = self.alt[3]
        os.environ.pop("FURIOS_BATTERY_SETTING_FILE", None)
        os.environ.pop("FURIOS_BATTERY_ICON", None)
        os.environ["PATH"] = self.alter_pfad
        for ordner, _, dateien in os.walk(self.tmp, topdown=False):
            for datei in dateien:
                os.unlink(os.path.join(ordner, datei))
            os.rmdir(ordner)

    # -- Helfer ------------------------------------------------------------
    def battery(self, status="Charging", ampere=1.2, volt=4.3, percent=80):
        werte = {"status": status,
                 "current_now": str(int(ampere * 1e6)),
                 "voltage_now": str(int(volt * 1e6)),
                 "capacity": str(percent)}
        for name, wert in werte.items():
            with open(os.path.join(self.sysfs, name), "w") as fh:
                fh.write(wert + "\n")

    def set_theme(self, name):
        with open(self.setting, "w") as fh:
            fh.write(name + "\n")

    def alle_themes(self, base="base"):
        """Die drei Huellenfarben, wie sie frueher write_themes schrieb."""
        return [b.write_theme(base, farbe, None) for farbe in b.BUCKETS]

    def make_theme(self, name, dark=True):
        gtk3 = os.path.join(self.themes, name, "gtk-3.0")
        os.makedirs(gtk3, exist_ok=True)
        with open(os.path.join(gtk3, "gtk.css"), "w") as fh:
            fh.write("/* the user's own */\n")
        if dark:
            with open(os.path.join(gtk3, "gtk-dark.css"), "w") as fh:
                fh.write("/* the user's own, dark */\n")

    def run_cmd(self, *argv):
        aus, err = io.StringIO(), io.StringIO()
        with redirect_stdout(aus), redirect_stderr(err):
            rc = b.main(list(argv))
        return rc, aus.getvalue(), err.getvalue()


class Messung(Basis):
    def test_liest_watt(self):
        self.battery(ampere=1.2, volt=4.3)
        mess = b.read_battery()
        self.assertAlmostEqual(mess["watt"], 5.16, places=2)
        self.assertTrue(mess["charging"])
        self.assertTrue(mess["moving"])

    def test_fehlende_datei_ist_none(self):
        self.assertIsNone(b.read_battery())

    def test_unlesbarer_wert_ist_none(self):
        self.battery()
        with open(os.path.join(self.sysfs, "current_now"), "w") as fh:
            fh.write("keine zahl\n")
        self.assertIsNone(b.read_battery())

    def test_vorzeichen_wird_verworfen(self):
        """Some drivers count discharge negative. Direction comes from
        `status`, never from the sign, or a discharging phone would read as
        -3 W and land in a bucket by arithmetic accident."""
        self.battery(status="Discharging", ampere=-0.8, volt=3.9)
        mess = b.read_battery()
        self.assertAlmostEqual(mess["watt"], 3.12, places=2)
        self.assertFalse(mess["charging"])
        self.assertTrue(mess["moving"])

    def test_voll_bewegt_sich_nicht(self):
        self.battery(status="Full", ampere=0.0, volt=4.4)
        self.assertFalse(b.read_battery()["moving"])

    def test_not_charging_bewegt_sich_nicht(self):
        self.battery(status="Not charging", ampere=0.0, volt=4.4)
        self.assertFalse(b.read_battery()["moving"])

    def test_unplausibel_wird_erkannt(self):
        """A driver reporting milliamps where the class says microamps would
        make every charge look like a thousand watts - and the icon
        permanently green."""
        self.battery(ampere=1200.0, volt=4.3)
        self.assertFalse(b.read_battery()["plausible"])

    def test_median(self):
        self.assertEqual(b.median([3, 1, 2]), 2)
        self.assertEqual(b.median([4, 1, 2, 3]), 2.5)
        self.assertIsNone(b.median([]))


class Schwellen(Basis):
    def setUp(self):
        super().setUp()
        self.cfg = dict(b.DEFAULTS)

    def test_laden_drei_stufen(self):
        self.assertEqual(b.bucket_for(8.0, True, self.cfg), "green")
        self.assertEqual(b.bucket_for(5.0, True, self.cfg), "amber")
        self.assertEqual(b.bucket_for(1.0, True, self.cfg), "red")

    def test_genau_auf_der_schwelle_ist_die_bessere_farbe(self):
        self.assertEqual(b.bucket_for(7.0, True, self.cfg), "green")
        self.assertEqual(b.bucket_for(3.0, True, self.cfg), "amber")

    def test_entladen_bleibt_normalerweise_weiss(self):
        """White is the normal state on battery: a phone doing what a phone
        does says nothing, and only an unusual drain speaks up."""
        self.assertIsNone(b.bucket_for(0.2, False, self.cfg))
        self.assertIsNone(b.bucket_for(2.0, False, self.cfg))
        self.assertEqual(b.bucket_for(3.5, False, self.cfg), "amber")
        self.assertEqual(b.bucket_for(9.0, False, self.cfg), "red")

    def test_entladen_kennt_kein_gruen(self):
        """Green on battery would be a colour on all day - no signal at
        all."""
        for watt in (0.0, 0.5, 1.0, 2.9, 3.5, 12.0):
            self.assertNotEqual(b.bucket_for(watt, False, self.cfg), "green")

    def test_hysterese_haelt_gruen(self):
        """6.5 W is under the 7 W it took to go green, but not far enough
        under to give it up - the reading swings that much on its own."""
        self.assertEqual(b.bucket_for(6.5, True, self.cfg, "green"), "green")
        self.assertEqual(b.bucket_for(6.2, True, self.cfg, "green"), "amber")

    def test_hysterese_haelt_rot(self):
        self.assertEqual(b.bucket_for(3.2, True, self.cfg, "red"), "red")
        self.assertEqual(b.bucket_for(3.4, True, self.cfg, "red"), "amber")

    def test_hysterese_aus_gelb_kostet_mehr(self):
        self.assertEqual(b.bucket_for(7.5, True, self.cfg, "amber"), "amber")
        self.assertEqual(b.bucket_for(7.8, True, self.cfg, "amber"), "green")

    def test_aus_weiss_heraus_kostet_die_farbe_einen_zehntel_mehr(self):
        """Otherwise the icon would light up on the noise of a reading that
        sits on the threshold."""
        self.assertIsNone(b.bucket_for(3.2, False, self.cfg, None))
        self.assertEqual(b.bucket_for(3.4, False, self.cfg, None), "amber")

    def test_hysterese_beim_entladen_aus_gelb_und_rot(self):
        # aus gelb heraus nach unten und nach oben
        self.assertEqual(b.bucket_for(2.8, False, self.cfg, "amber"), "amber")
        self.assertIsNone(b.bucket_for(2.6, False, self.cfg, "amber"))
        self.assertEqual(b.bucket_for(5.4, False, self.cfg, "amber"), "amber")
        self.assertEqual(b.bucket_for(5.6, False, self.cfg, "amber"), "red")
        # und aus rot heraus
        self.assertEqual(b.bucket_for(4.6, False, self.cfg, "red"), "red")
        self.assertEqual(b.bucket_for(4.4, False, self.cfg, "red"), "amber")
        self.assertIsNone(b.bucket_for(1.0, False, self.cfg, "red"))

    def test_abgeschaltet_heisst_keine_farbe(self):
        self.battery()
        cfg = dict(self.cfg, charging=False)
        self.assertIsNone(b.wanted_bucket(b.read_battery(), cfg))

    def test_entladen_nur_wenn_gewollt(self):
        self.battery(status="Discharging", ampere=1.5, volt=3.9)   # 5.85 W
        mess = b.read_battery()
        self.assertIsNone(b.wanted_bucket(mess, self.cfg))
        self.assertEqual(b.wanted_bucket(mess, dict(self.cfg, discharging=True)),
                         "red")

    def test_gewoehnliches_entladen_faerbt_auch_dann_nichts(self):
        """The option is "say something when it is unusual", not "be
        coloured whenever the cable is out"."""
        self.battery(status="Discharging", ampere=0.2, volt=3.9)   # 0.78 W
        self.assertIsNone(b.wanted_bucket(b.read_battery(),
                                          dict(self.cfg, discharging=True)))

    def test_voll_bekommt_keine_farbe(self):
        self.battery(status="Full", ampere=0.0, volt=4.4)
        self.assertIsNone(b.wanted_bucket(b.read_battery(), self.cfg))

    def test_unlesbar_bekommt_keine_farbe(self):
        self.assertIsNone(b.wanted_bucket(None, self.cfg))

    def test_unplausibel_bekommt_keine_farbe(self):
        self.battery(ampere=900.0, volt=4.3)
        self.assertIsNone(b.wanted_bucket(b.read_battery(), self.cfg))


class Fuellstand(Basis):
    """Die Fuellung sagt etwas anderes als die Huelle: wie voll, nicht wie
    schnell."""

    def setUp(self):
        super().setUp()
        self.cfg = dict(b.DEFAULTS)

    def test_drei_bereiche(self):
        self.assertIsNone(b.level_for(85, self.cfg))
        self.assertIsNone(b.level_for(61, self.cfg))
        self.assertEqual(b.level_for(59, self.cfg), "amber")
        self.assertEqual(b.level_for(16, self.cfg), "amber")
        self.assertEqual(b.level_for(14, self.cfg), "red")
        self.assertEqual(b.level_for(0, self.cfg), "red")

    def test_die_grenze_selbst_gehoert_zur_besseren_farbe(self):
        self.assertIsNone(b.level_for(60, self.cfg))
        self.assertEqual(b.level_for(15, self.cfg), "amber")

    def test_hysterese_ueber_zwei_punkte(self):
        """A percentage stepping across 60 and back must not restyle every
        app twice a minute."""
        self.assertEqual(b.level_for(61, self.cfg, "amber"), "amber")
        self.assertIsNone(b.level_for(63, self.cfg, "amber"))
        self.assertEqual(b.level_for(14, self.cfg, "red"), "red")
        self.assertEqual(b.level_for(16, self.cfg, "red"), "red")
        self.assertEqual(b.level_for(18, self.cfg, "red"), "amber")

    def test_unlesbarer_ladestand_faerbt_nichts(self):
        """Not "nearly empty": a phone whose capacity cannot be read must
        not have its icon painted as a warning."""
        self.assertIsNone(b.level_for(None, self.cfg))

    def test_abschaltbar(self):
        self.assertIsNone(b.level_for(5, dict(self.cfg, level=False)))

    def test_aus_der_messung(self):
        self.battery(percent=42)
        self.assertEqual(b.wanted_level(b.read_battery(), self.cfg), "amber")
        self.assertIsNone(b.wanted_level(None, self.cfg))

    def test_fehlende_capacity_datei(self):
        self.battery()
        os.unlink(os.path.join(self.sysfs, "capacity"))
        self.assertIsNone(b.read_battery()["percent"])

    def test_die_fuellung_haengt_nicht_am_ladezustand(self):
        """Independent of the shell on purpose: a nearly empty battery says
        so whether it is charging, draining or full."""
        for zustand in ("Charging", "Discharging", "Full", "Not charging"):
            self.battery(status=zustand, percent=9)
            self.assertEqual(b.wanted_level(b.read_battery(), self.cfg), "red",
                             zustand)


class Symbolfamilien(Basis):
    """Welches Symbol auf dem Schirm ist, entscheidet, ob es zwei Haelften
    zu faerben gibt."""

    def setUp(self):
        super().setUp()
        self.icons = os.path.join(self.tmp, "icons", "Adwaita",
                                  "symbolic", "status")
        os.makedirs(self.icons)
        self.alte_dirs = list(b.ICON_DIRS)
        b.ICON_DIRS[:] = [os.path.join(self.tmp, "icons")]

    def tearDown(self):
        b.ICON_DIRS[:] = self.alte_dirs
        super().tearDown()

    def icon(self, name, mit_klasse):
        pfad = os.path.join(self.icons, name + ".svg")
        with open(pfad, "w") as fh:
            fh.write('<svg>%s<path d="m 0 0"/></svg>'
                     % ('<path class="success" d="m 5 7"/>' if mit_klasse else ""))
        return pfad

    def test_zwei_pfade_lassen_sich_getrennt_faerben(self):
        self.icon("battery-level-90-charging-symbolic", True)
        self.assertTrue(b.icon_is_split("battery-level-90-charging-symbolic"))

    def test_ein_pfad_nicht(self):
        """Adwaitas zwoelf Entlade-Symbole sind EIN Pfad: `color` faerbt das
        ganze Symbol, die Palette nichts."""
        self.icon("battery-level-90-symbolic", False)
        self.assertFalse(b.icon_is_split("battery-level-90-symbolic"))

    def test_die_datei_entscheidet_nicht_der_name(self):
        """Ein Symbolthema kann alles anders bauen - gelesen wird die
        Datei, geraten nur, wenn es keine gibt."""
        self.icon("battery-full-charging-symbolic", False)
        self.assertFalse(b.icon_is_split("battery-full-charging-symbolic"))

    def test_ohne_datei_entscheidet_der_name(self):
        self.assertTrue(b.icon_is_split("battery-level-40-charging-symbolic"))
        self.assertTrue(b.icon_is_split("battery-level-40-plugged-in-symbolic"))
        self.assertFalse(b.icon_is_split("battery-level-40-symbolic"))

    def test_ohne_namen_entscheidet_der_ladezustand(self):
        self.assertTrue(b.icon_is_split(None, charging=True))
        self.assertFalse(b.icon_is_split(None, charging=False))
        self.assertIsNone(b.find_icon(None))

    def test_widersprechende_quellen_faerben_die_huelle_nicht(self):
        """Seen on the phone: sysfs "Charging" at 1.8 W, UPower
        "discharging" at 0 W, and phosh drawing the icon without a bolt. A
        charging colour on that icon answers a question the picture does
        not ask."""
        self.battery(status="Charging", ampere=0.2, volt=4.3)
        mess = b.read_battery()
        cfg = dict(b.DEFAULTS)
        self.assertEqual(b.wanted_bucket(mess, cfg), "red")
        self.assertEqual(
            b.wanted_bucket(mess, cfg, icon="battery-level-90-charging-symbolic"),
            "red")
        self.assertIsNone(
            b.wanted_bucket(mess, cfg, icon="battery-full-symbolic"))

    def test_einig_ohne_symbol_und_ohne_messung(self):
        self.battery()
        self.assertTrue(b.sources_agree(b.read_battery(), None))
        self.assertTrue(b.sources_agree(None, "battery-full-symbolic"))

    def test_der_ladestand_bleibt_davon_unberuehrt(self):
        """How full it is, both sources agree on."""
        self.battery(status="Charging", ampere=0.2, volt=4.3, percent=9)
        self.assertEqual(b.wanted_level(b.read_battery(), dict(b.DEFAULTS)),
                         "red")

    def test_eine_haelfte_bekommt_die_dringlichere_farbe(self):
        self.assertEqual(b.merge_colours("green", "red"), "red")
        self.assertEqual(b.merge_colours("red", "amber"), "red")
        self.assertEqual(b.merge_colours(None, "amber"), "amber")
        self.assertEqual(b.merge_colours("green", None), "green")
        self.assertIsNone(b.merge_colours(None, None))

    def test_der_umweg_fuer_die_tests_ist_genau_einer(self):
        os.environ["FURIOS_BATTERY_ICON"] = "battery-full-symbolic"
        self.assertEqual(b.upower_icon(), "battery-full-symbolic")
        os.environ["FURIOS_BATTERY_ICON"] = ""
        self.assertIsNone(b.upower_icon())

    def test_upower_wird_gefragt_weil_phosh_es_auch_tut(self):
        os.environ.pop("FURIOS_BATTERY_ICON", None)
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        with open(os.path.join(bin_dir, "upower"), "w") as fh:
            fh.write("#!/bin/sh\necho \"  icon-name: 'battery-full-symbolic'\"\n")
        os.chmod(os.path.join(bin_dir, "upower"), 0o755)
        os.environ["PATH"] = bin_dir + ":" + os.environ["PATH"]
        self.assertEqual(b.upower_icon(), "battery-full-symbolic")

    def test_ohne_upower_ist_es_kein_absturz(self):
        os.environ.pop("FURIOS_BATTERY_ICON", None)
        os.environ["PATH"] = os.path.join(self.tmp, "leer")
        self.assertIsNone(b.upower_icon())


class Namen(Basis):
    def test_eigenes_theme_wird_erkannt(self):
        self.assertEqual(b.base_name(b.theme_name("adw-gtk3", "green")),
                         "adw-gtk3")
        # And the ones an older version of the rule wrote, with a different
        # token or none at all - otherwise an upgrade would take somebody's
        # own theme to be "adw-gtk3-batt-green".
        self.assertEqual(b.base_name("adw-gtk3-batt-red"), "adw-gtk3")
        self.assertEqual(b.base_name("adw-gtk3-batt9f9f-red"), "adw-gtk3")

    def test_fremdes_theme_bleibt(self):
        self.assertEqual(b.base_name("adw-gtk3"), "adw-gtk3")
        self.assertEqual(b.base_name("Yaru-batt-blue"), "Yaru-batt-blue")
        self.assertEqual(b.base_name("batt-green"), "batt-green")
        self.assertEqual(b.base_name(""), "")

    def test_name_zusammensetzen(self):
        self.assertEqual(b.theme_name("adw-gtk3", "amber"),
                         "adw-gtk3-batt%s-amber-none" % b.TOKEN)
        self.assertEqual(b.theme_name("adw-gtk3", None, "red"),
                         "adw-gtk3-batt%s-none-red" % b.TOKEN)
        # Beide Haelften sind unabhaengig, und der Name sagt beide.
        self.assertEqual(b.colours_of(b.theme_name("adw-gtk3", "green", "red")),
                         ("green", "red"))
        self.assertEqual(b.colours_of(b.theme_name("adw-gtk3", None, "amber")),
                         (None, "amber"))
        self.assertEqual(b.colours_of("adw-gtk3"), ("", ""))

    def test_hin_und_zurueck(self):
        for basis in ("adw-gtk3", "Adwaita", "a-b-c"):
            for bucket in b.BUCKETS:
                self.assertEqual(b.base_name(b.theme_name(basis, bucket)), basis)


class Themes(Basis):
    def test_schreibt_drei(self):
        self.make_theme("base")
        namen = self.alle_themes()
        self.assertEqual(len(namen), 3)
        for name in namen:
            pfad = os.path.join(self.themes, name, "gtk-3.0", "gtk.css")
            inhalt = open(pfad).read()
            self.assertIn("phosh-battery-info image", inhalt)
            self.assertIn("@import", inhalt)

    def test_farben_stimmen(self):
        self.make_theme("base")
        self.alle_themes()
        for bucket, farbe in b.COLORS.items():
            pfad = os.path.join(self.themes, b.theme_name("base", bucket),
                                "gtk-3.0", "gtk.css")
            self.assertIn(farbe, open(pfad).read())

    def test_die_beiden_haelften_stehen_getrennt_in_der_regel(self):
        """The icon is two paths and now says two things: the shell follows
        `color` (how fast), the filling comes from the symbolic palette (how
        full). Colouring only the first left a white filling in a red
        battery - which is what the phone showed on 15.9.2026."""
        self.make_theme("base")
        b.write_theme("base", "red", "amber")
        inhalt = open(os.path.join(self.themes,
                                   b.theme_name("base", "red", "amber"),
                                   "gtk-3.0", "gtk.css")).read()
        self.assertIn("color: %s;" % b.COLORS["red"], inhalt)
        # All three palette names, because below 20 % the filling is warning
        # and error rather than success.
        for name in ("success", "warning", "error"):
            self.assertIn("%s %s" % (name, b.COLORS["amber"]), inhalt)

    def test_was_nichts_sagt_steht_auch_nicht_da(self):
        """"No colour" is said by leaving the declaration out - naming a
        white would be guessing at a foreground we cannot read."""
        self.make_theme("base")
        b.write_theme("base", "red", None)
        nur_huelle = open(os.path.join(self.themes,
                                       b.theme_name("base", "red"),
                                       "gtk-3.0", "gtk.css")).read()
        self.assertIn("color:", nur_huelle)
        self.assertNotIn("-gtk-icon-palette", nur_huelle)
        b.write_theme("base", None, "red")
        nur_fuellung = open(os.path.join(self.themes,
                                         b.theme_name("base", None, "red"),
                                         "gtk-3.0", "gtk.css")).read()
        self.assertIn("-gtk-icon-palette", nur_fuellung)
        self.assertNotIn("  color:", nur_fuellung)

    def test_ohne_beides_gibt_es_kein_theme(self):
        self.make_theme("base")
        self.assertEqual(b.css_rule(None, None), "")
        self.assertIsNone(b.write_theme("base", None, None))

    def test_die_regel_ist_gueltiges_gtk3_css(self):
        """Checked against GTK itself rather than by reading it: an unknown
        property is dropped with a warning nobody sees, and the icon would
        simply stay half-coloured."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk
        except (ImportError, ValueError):                 # pragma: no cover
            self.skipTest("kein GTK3")
        self.make_theme("base")
        self.alle_themes()
        pfad = os.path.join(self.themes, b.theme_name("base", "green"), "gtk-3.0",
                            "gtk.css")
        text = open(pfad).read().split("*/", 1)[1]        # ohne @import
        fehler = []
        prov = Gtk.CssProvider()
        prov.connect("parsing-error", lambda p, s, e: fehler.append(e.message))
        prov.load_from_data(text.encode())
        self.assertEqual([], fehler)

    def test_ohne_dunkles_blatt_wird_keines_erfunden(self):
        """The trap that would change the whole look of the phone: GTK3 uses
        gtk-dark.css when it exists. Writing one for a theme that has none
        would put the LIGHT stylesheet behind dark mode."""
        self.make_theme("base", dark=False)
        self.alle_themes()
        pfad = os.path.join(self.themes, b.theme_name("base", "green"), "gtk-3.0",
                            "gtk-dark.css")
        self.assertFalse(os.path.exists(pfad))

    def test_dunkles_blatt_verschwindet_wieder(self):
        self.make_theme("base", dark=True)
        self.alle_themes()
        pfad = os.path.join(self.themes, b.theme_name("base", "green"), "gtk-3.0",
                            "gtk-dark.css")
        self.assertTrue(os.path.exists(pfad))
        self.make_theme("base", dark=False)
        os.unlink(os.path.join(self.themes, "base", "gtk-3.0", "gtk-dark.css"))
        self.alle_themes()
        self.assertFalse(os.path.exists(pfad))

    def test_eingebautes_adwaita(self):
        hell, dunkel = b.base_css("Adwaita")
        self.assertTrue(hell.startswith("resource:"))
        self.assertTrue(dunkel.endswith("gtk-contained-dark.css"))

    def test_unbekanntes_theme_wird_abgelehnt(self):
        self.assertEqual(b.base_css("gibt-es-nicht"), (None, None))
        self.assertIsNone(b.write_theme("gibt-es-nicht", "green", None))
        self.assertFalse(b.can_theme("gibt-es-nicht"))

    def test_import_verweist_auf_das_original(self):
        """@import, not a copy: everything the base theme loads by relative
        path has to keep resolving against where IT lives."""
        self.make_theme("base")
        self.alle_themes()
        inhalt = open(os.path.join(self.themes, b.theme_name("base", "red"),
                                   "gtk-3.0", "gtk.css")).read()
        self.assertIn("file://" + os.path.join(self.themes, "base",
                                               "gtk-3.0", "gtk.css"), inhalt)

    def test_entfernen_nimmt_nur_unsere(self):
        self.make_theme("base")
        self.alle_themes()
        # Somebody else's theme that happens to fit the pattern.
        self.make_theme("fremd-batt-green")
        weg = b.remove_themes()
        self.assertEqual(weg, 3)
        self.assertTrue(os.path.isdir(os.path.join(self.themes, "base")))
        self.assertTrue(os.path.isdir(os.path.join(self.themes,
                                                   "fremd-batt-green")))

    def test_alte_generationen_werden_erkannt_und_nur_die(self):
        """An upgrade must clear out what the old rule wrote without
        touching what is in use - the names differ by the token, which is
        the whole reason it is in the name."""
        self.make_theme("base")
        aktuell = self.alle_themes()
        # Was eine aeltere Fassung hinterlassen haette:
        for alt_name in ("base-batt-green", "base-batt9f9f-red-none"):
            gtk3 = os.path.join(self.themes, alt_name, "gtk-3.0")
            os.makedirs(gtk3)
            with open(os.path.join(gtk3, "gtk.css"), "w") as fh:
                fh.write("/* battctl */\n")
        veraltet = b.stale_themes()
        self.assertEqual(sorted(veraltet),
                         ["base-batt-green", "base-batt9f9f-red-none"])
        self.assertEqual(b.remove_themes(nur=veraltet), 2)
        for name in aktuell:
            self.assertTrue(os.path.isdir(os.path.join(self.themes, name)), name)
        self.assertTrue(os.path.isdir(os.path.join(self.themes, "base")))

    def test_ohne_verzeichnis_gibt_es_auch_nichts_veraltetes(self):
        b.THEMES = os.path.join(self.tmp, "gibt-es-nicht")
        b.THEME_DIRS[:] = [b.THEMES]
        self.assertEqual(b.stale_themes(), [])

    def test_entfernen_ohne_verzeichnis(self):
        b.THEMES = os.path.join(self.tmp, "gibt-es-nicht")
        self.assertEqual(b.remove_themes(), 0)

    def test_entfernen_uebergeht_was_es_nicht_lesen_kann(self):
        """A directory that fits the name but holds no stylesheet of ours is
        not ours to delete."""
        os.makedirs(os.path.join(self.themes, b.theme_name("base", "green"), "gtk-3.0"))
        self.assertEqual(b.remove_themes(), 0)
        self.assertTrue(os.path.isdir(os.path.join(self.themes,
                                                   b.theme_name("base", "green"))))

    def test_eingebautes_theme_wird_per_resource_importiert(self):
        """Adwaita has no files on disk - GTK3 carries it as a resource, and
        the import has to say so rather than pointing at a path."""
        namen = self.alle_themes("Adwaita")
        self.assertEqual(len(namen), 3)
        inhalt = open(os.path.join(self.themes, b.theme_name("Adwaita", "green"),
                                   "gtk-3.0", "gtk.css")).read()
        self.assertIn('@import url("resource:///org/gtk/libgtk/theme/Adwaita/',
                      inhalt)
        self.assertNotIn("file://", inhalt)


class Einstellung(Basis):
    def test_lesen_und_schreiben(self):
        s = b.Setting()
        self.assertEqual(s.get(), "base")
        self.assertTrue(s.set(b.theme_name("base", "green")))
        self.assertEqual(s.get(), b.theme_name("base", "green"))

    def test_fehlende_datei_ist_leer(self):
        os.unlink(self.setting)
        self.assertEqual(b.Setting().get(), "")

    def _fake_gsettings(self, rc=0, ausgabe="'adw-gtk3'"):
        """A gsettings on PATH, so the path the phone really takes is tested
        and not only the file the tests use."""
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        pfad = os.path.join(bin_dir, "gsettings")
        with open(pfad, "w") as fh:
            fh.write("#!/bin/sh\n"
                     'if [ "$1" = get ]; then echo "%s"; fi\n'
                     "echo \"$@\" >> %s/aufrufe\n"
                     "exit %d\n" % (ausgabe, self.tmp, rc))
        os.chmod(pfad, 0o755)
        os.environ.pop("FURIOS_BATTERY_SETTING_FILE", None)
        os.environ["PATH"] = bin_dir + ":" + os.environ["PATH"]
        return os.path.join(self.tmp, "aufrufe")

    def test_echtes_gsettings_lesen_und_schreiben(self):
        aufrufe = self._fake_gsettings()
        s = b.Setting()
        self.assertEqual(s.get(), "adw-gtk3")
        self.assertTrue(s.set("adw-gtk3-batt-green"))
        zeilen = open(aufrufe).read()
        self.assertIn("get org.gnome.desktop.interface gtk-theme", zeilen)
        self.assertIn("set org.gnome.desktop.interface gtk-theme "
                      "adw-gtk3-batt-green", zeilen)

    def test_gescheitertes_gsettings_meldet_sich(self):
        self._fake_gsettings(rc=3)
        self.assertFalse(b.Setting().set("egal"))

    def test_fehlendes_gsettings_ist_kein_absturz(self):
        bin_dir = os.path.join(self.tmp, "leer")
        os.makedirs(bin_dir, exist_ok=True)
        os.environ.pop("FURIOS_BATTERY_SETTING_FILE", None)
        os.environ["PATH"] = bin_dir
        s = b.Setting()
        self.assertEqual(s.get(), "")
        self.assertFalse(s.set("egal"))


class Konfiguration(Basis):
    def test_defaults_ohne_datei(self):
        self.assertEqual(b.load_config(), b.DEFAULTS)

    def test_speichern_und_lesen(self):
        cfg = dict(b.DEFAULTS, discharging=True, charge_green_w=9.5)
        b.save_config(cfg)
        self.assertEqual(b.load_config()["charge_green_w"], 9.5)
        self.assertTrue(b.load_config()["discharging"])

    def test_kaputte_datei_gibt_defaults(self):
        with open(b.CONFIG, "w") as fh:
            fh.write("{ das ist kein json")
        self.assertEqual(b.load_config(), b.DEFAULTS)

    def test_fremde_schluessel_werden_ignoriert(self):
        with open(b.CONFIG, "w") as fh:
            json.dump({"charge_green_w": 8.0, "unsinn": 1}, fh)
        cfg = b.load_config()
        self.assertEqual(cfg["charge_green_w"], 8.0)
        self.assertNotIn("unsinn", cfg)

    def test_falscher_typ_wird_ignoriert(self):
        with open(b.CONFIG, "w") as fh:
            json.dump({"charge_green_w": "viel"}, fh)
        self.assertEqual(b.load_config()["charge_green_w"],
                         b.DEFAULTS["charge_green_w"])

    def test_ganze_zahl_gilt_als_kommazahl(self):
        with open(b.CONFIG, "w") as fh:
            json.dump({"charge_green_w": 8}, fh)
        self.assertEqual(b.load_config()["charge_green_w"], 8.0)

    def test_liste_statt_objekt(self):
        with open(b.CONFIG, "w") as fh:
            json.dump([1, 2], fh)
        self.assertEqual(b.load_config(), b.DEFAULTS)


class Befehle(Basis):
    def test_hilfe(self):
        for arg in ([], ["--help"], ["help"]):
            rc, aus, _ = self.run_cmd(*arg)
            self.assertEqual(rc, 0)
            self.assertIn("battctl status", aus)

    def test_unbekannter_befehl(self):
        rc, _, err = self.run_cmd("fliegen")
        self.assertEqual(rc, 2)
        self.assertIn("Unknown command", err)

    def test_status_lesbar(self):
        self.battery(ampere=1.9, volt=4.2)
        self.make_theme("base")
        rc, aus, _ = self.run_cmd("status")
        self.assertEqual(rc, 0)
        self.assertIn("state:        Charging", aus)
        self.assertIn("7.98 W", aus)

    def test_status_ohne_akku(self):
        rc, aus, _ = self.run_cmd("status")
        self.assertEqual(rc, 1)
        self.assertIn("not readable", aus)

    def test_status_json(self):
        self.battery(ampere=1.9, volt=4.2)
        self.make_theme("base")
        rc, aus, _ = self.run_cmd("status", "--json")
        daten = json.loads(aus)
        self.assertEqual(rc, 0)
        self.assertEqual(daten["bucket"], "green")
        self.assertEqual(daten["base_theme"], "base")
        self.assertEqual(daten["showing"], "none")
        self.assertTrue(daten["can_theme"])

    def test_status_meldet_untaugliches_theme(self):
        self.battery()
        rc, aus, _ = self.run_cmd("status")
        self.assertIn("no GTK3 stylesheet", aus)
        self.assertEqual(rc, 0)

    def test_status_kennt_die_laufende_farbe(self):
        self.battery(ampere=0.2, volt=4.2)
        self.make_theme("base")
        self.set_theme(b.theme_name("base", "green"))
        _, aus, _ = self.run_cmd("status")
        self.assertIn("shell:        green", aus)
        self.assertIn("base theme:   base", aus)

    def test_config_zeigt_alles(self):
        rc, aus, _ = self.run_cmd("config")
        self.assertEqual(rc, 0)
        self.assertIn("charge_green_w: 7.0", aus)

    def test_config_schaltet(self):
        rc, aus, _ = self.run_cmd("config", "discharging", "on")
        self.assertEqual(rc, 0)
        self.assertIn("discharging: True", aus)
        self.assertTrue(b.load_config()["discharging"])

    def test_config_nimmt_bindestriche(self):
        rc, _, _ = self.run_cmd("config", "charge-green-w", "9")
        self.assertEqual(rc, 0)
        self.assertEqual(b.load_config()["charge_green_w"], 9.0)

    def test_config_ganzzahl_bleibt_ganzzahl(self):
        self.run_cmd("config", "dwell_s", "90")
        self.assertIsInstance(b.load_config()["dwell_s"], int)

    def test_config_weist_unsinn_ab(self):
        for argv in (("config", "discharging", "vielleicht"),
                     ("config", "charge_green_w", "viel"),
                     ("config", "charge_green_w", "-3"),
                     ("config", "gibt_es_nicht", "1"),
                     ("config", "zu", "viele", "worte")):
            rc, _, err = self.run_cmd(*argv)
            self.assertEqual(rc, 2, argv)
            self.assertTrue(err)

    def test_config_laesst_schwellen_nicht_kreuzen(self):
        rc, _, err = self.run_cmd("config", "charge_green_w", "2")
        self.assertEqual(rc, 2)
        self.assertIn("above", err)
        self.assertEqual(b.load_config()["charge_green_w"], 7.0)
        rc, _, err = self.run_cmd("config", "drain_amber_w", "9")
        self.assertEqual(rc, 2)
        self.assertIn("below", err)
        rc, _, err = self.run_cmd("config", "level_red_pct", "70")
        self.assertEqual(rc, 2)
        self.assertIn("below", err)

    def test_reset_setzt_zurueck(self):
        self.set_theme(b.theme_name("base", "amber"))
        rc, _, _ = self.run_cmd("reset")
        self.assertEqual(rc, 0)
        self.assertEqual(b.Setting().get(), "base")

    def test_reset_ist_wiederholbar(self):
        self.assertEqual(self.run_cmd("reset")[0], 0)
        self.assertEqual(b.Setting().get(), "base")

    def test_restore_raeumt_alles(self):
        self.make_theme("base")
        self.alle_themes()
        b.save_config(dict(b.DEFAULTS, discharging=True))
        self.set_theme(b.theme_name("base", "red"))
        rc, aus, _ = self.run_cmd("restore")
        self.assertEqual(rc, 0)
        self.assertIn("3 colour theme(s) removed", aus)
        self.assertEqual(b.Setting().get(), "base")
        self.assertFalse(os.path.exists(b.CONFIG))
        self.assertEqual(b.load_config(), b.DEFAULTS)

    def test_restore_ohne_alles(self):
        rc, _, _ = self.run_cmd("restore")
        self.assertEqual(rc, 0)


class Mitschnitt(Basis):
    """`battctl watch` - das Messwerkzeug fuer die Schwellen."""

    def test_quantile(self):
        werte = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(b.quantil(werte, 0.5), 6)
        self.assertEqual(b.quantil(werte, 0.9), 9)
        self.assertEqual(b.quantil(werte, 1.0), 10)
        self.assertEqual(b.quantil([7], 0.9), 7)
        self.assertIsNone(b.quantil([], 0.5))

    def test_schreibt_zeilen_und_eine_zusammenfassung(self):
        self.battery(status="Discharging", ampere=0.5, volt=3.9)
        pfad = os.path.join(self.tmp, "log.csv")
        rc, aus, _ = self.run_cmd("watch", "0.2", "--interval", "0.05",
                                  "--csv", pfad)
        self.assertEqual(rc, 0)
        self.assertIn("time,state,watt,percent,screen", aus)
        self.assertIn("Discharging:", aus)
        self.assertIn("median", aus)
        zeilen = open(pfad).read().splitlines()
        self.assertGreater(len(zeilen), 1)
        self.assertTrue(zeilen[1].startswith("2"))      # ISO-Datum

    def test_eine_wackelnde_messreihe_sagt_es_selbst(self):
        """A calibration run on a worn port should say so rather than hand
        over a median of noise."""
        self.battery(status="Charging", ampere=1.2, volt=4.3)

        echte_battery = self.battery
        zaehler = {"n": 0}

        def wechselnd(*a, **kw):
            zaehler["n"] += 1
            echte_battery(status="Charging" if zaehler["n"] % 2 else
                          "Discharging", ampere=1.2, volt=4.3)

        # Der Zustand wechselt zwischen den Messungen.
        import threading
        stop = threading.Event()

        def ruettler():
            while not stop.is_set():
                wechselnd()
                stop.wait(0.02)

        t = threading.Thread(target=ruettler)
        t.start()
        try:
            _rc, aus, _ = self.run_cmd("watch", "0.4", "--interval", "0.05")
        finally:
            stop.set()
            t.join()
        self.assertIn("direction changed", aus)
        self.assertIn("not a baseline", aus)

    def test_unlesbarer_akku_erzeugt_keine_zeilen(self):
        rc, aus, _ = self.run_cmd("watch", "0.1", "--interval", "0.05")
        self.assertEqual(rc, 0)
        self.assertNotIn("Discharging:", aus)

    # -------------------------------------------------- Auswertung

    def log(self, zeilen):
        pfad = os.path.join(self.tmp, "log.csv")
        with open(pfad, "w") as fh:
            fh.write("time,state,watt,percent,screen\n")
            for i, (zustand, watt, licht) in enumerate(zeilen):
                fh.write("2026-09-15T12:%02d:00,%s,%.3f,80,%s\n"
                         % (i % 60, zustand, watt, licht))
        return pfad

    def test_liest_ueber_kaputte_zeilen_hinweg(self):
        pfad = self.log([("Discharging", 1.0, 100)])
        with open(pfad, "a") as fh:
            fh.write("abgeschnitten\n2026,Discharging,keine-zahl,80,100\n")
        zeilen, fehler = b.read_log(pfad)
        self.assertIsNone(fehler)
        self.assertEqual(len(zeilen), 1)

    def test_eine_fehlende_datei_ist_ein_satz_kein_absturz(self):
        zeilen, fehler = b.read_log(os.path.join(self.tmp, "gibts-nicht"))
        self.assertEqual([], zeilen)
        self.assertIn("gibts-nicht", fehler)

    def test_leeres_log(self):
        pfad = self.log([])
        _zeilen, fehler = b.read_log(pfad)
        self.assertIn("no readings", fehler)

    def test_die_bildschirmspalte_in_beiden_schreibweisen(self):
        """Der DPMS-Zustand des Panels, und - wo es den nicht gibt - die
        Helligkeit als Zahl."""
        zeilen, _ = b.read_log(self.log(
            [("Discharging", 1.0, "On"), ("Discharging", 1.0, "Off"),
             ("Discharging", 1.0, 700), ("Discharging", 1.0, 0),
             ("Discharging", 1.0, "?")]))
        self.assertEqual([z["screen"] for z in zeilen],
                         [True, False, True, False, None])

    def test_bildschirm_an_und_aus_sind_zwei_verteilungen(self):
        """Nur die eine bestimmt die Schwellen: dieses Symbol sieht nur,
        wer auf den Bildschirm schaut."""
        zeilen, _ = b.read_log(self.log(
            [("Discharging", 0.2, 0)] * 10 + [("Discharging", 3.0, 800)] * 10))
        gruppen, _wechsel = b.summarise(zeilen)
        self.assertEqual(len(gruppen["Discharging"]), 20)
        self.assertEqual(len(gruppen["Discharging, screen off"]), 10)
        self.assertEqual(b.quantil(gruppen["Discharging, screen on"], 0.5), 3.0)

    def test_richtungswechsel_werden_gezaehlt(self):
        zeilen, _ = b.read_log(self.log(
            [("Charging", 1.0, 100), ("Discharging", 1.0, 100),
             ("Discharging", 1.0, 100), ("Charging", 1.0, 100)]))
        self.assertEqual(b.summarise(zeilen)[1], 2)

    def test_der_vorschlag_braucht_genug_messungen(self):
        self.assertIsNone(b.suggestion([1.0] * 29))
        self.assertIsNone(b.suggestion([]))

    def test_und_genug_streuung(self):
        """All the same number means there is no "unusual" to find."""
        self.assertIsNone(b.suggestion([2.0] * 50))

    def test_der_vorschlag_ist_p90_und_p98(self):
        # Neunzig gewoehnliche Messungen, neun geschaeftige, eine Spitze.
        werte = [1.0] * 90 + [5.0] * 9 + [9.0]
        self.assertEqual(b.suggestion(werte), (1.0, 5.0))

    def test_summarise_nennt_beides_und_schreibt_nichts(self):
        pfad = self.log([("Discharging", 1.0, 700)] * 90
                        + [("Discharging", 5.0, 700)] * 9
                        + [("Discharging", 9.0, 700)])
        rc, aus, _ = self.run_cmd("summarise", pfad)
        self.assertEqual(rc, 0)
        self.assertIn("Suggested: drain_amber_w 1.0", aus)
        self.assertIn("drain_red_w 5.0", aus)
        self.assertEqual(b.load_config()["drain_amber_w"],
                         b.DEFAULTS["drain_amber_w"])

    def test_erst_mit_apply_werden_sie_gesetzt(self):
        pfad = self.log([("Discharging", 1.0, 700)] * 90
                        + [("Discharging", 5.0, 700)] * 9
                        + [("Discharging", 9.0, 700)])
        rc, aus, _ = self.run_cmd("summarise", pfad, "--apply")
        self.assertEqual(rc, 0)
        self.assertIn("Set.", aus)
        cfg = b.load_config()
        self.assertEqual(cfg["drain_amber_w"], 1.0)
        self.assertEqual(cfg["drain_red_w"], 5.0)

    def test_zu_wenige_messungen_setzen_nichts(self):
        pfad = self.log([("Discharging", 1.0, 700)] * 5)
        rc, aus, _ = self.run_cmd("summarise", pfad, "--apply")
        self.assertEqual(rc, 1)
        self.assertIn("Not enough", aus)
        self.assertEqual(b.load_config()["drain_amber_w"],
                         b.DEFAULTS["drain_amber_w"])

    def test_summarise_ohne_pfad(self):
        for argv in (("summarise",), ("summarise", "--wat", "x")):
            rc, _, err = self.run_cmd(*argv)
            self.assertEqual(rc, 2)
            self.assertIn("Usage", err)

    def test_summarise_liest_auch_die_amerikanische_schreibweise(self):
        pfad = self.log([("Discharging", 1.0, 700)])
        self.assertEqual(self.run_cmd("summarize", pfad)[0], 1)

    def test_unsinnige_argumente(self):
        rc, _, err = self.run_cmd("watch", "vielleicht")
        self.assertEqual(rc, 2)
        self.assertIn("Usage", err)


class DerLauf(Basis):
    """The daemon's decisions, driven by a clock the test holds."""

    def setUp(self):
        super().setUp()
        self.make_theme("base")
        self.battery(ampere=1.2, volt=4.3)          # 5.16 W -> amber
        self.d = b.Daemon(jetzt="base")

    def test_erste_farbe_kommt_sofort(self):
        self.assertTrue(self.d.tick(now=1000))
        self.assertEqual(self.d.showing[0], "amber")
        self.assertEqual(b.Setting().get(), b.theme_name("base", "amber"))

    def test_gleiche_farbe_schreibt_nicht(self):
        self.d.tick(now=1000)
        self.assertFalse(self.d.tick(now=2000))

    def test_wartezeit_haelt_die_farbe(self):
        """Every change restyles every GTK3 app, so a colour has to be worth
        it: under dwell_s the new one waits."""
        self.d.tick(now=1000)
        # Big enough that the median of the window crosses the threshold even
        # after hysteresis - otherwise this test passes because the colour did
        # not change at all, and says nothing about the waiting.
        self.battery(ampere=3.0, volt=4.3)          # 12.9 W -> green
        self.assertFalse(self.d.tick(now=1010))
        self.assertEqual(self.d.showing[0], "amber")
        self.assertEqual(b.Setting().get(), b.theme_name("base", "amber"))
        self.assertTrue(self.d.tick(now=1100))
        self.assertEqual(self.d.showing[0], "green")

    def test_median_glaettet_einen_ausreisser(self):
        for t in (1000, 1005, 1010):
            self.d.tick(now=t)
        self.battery(ampere=0.1, volt=4.3)          # ein Einbruch: 0.43 W
        self.d.tick(now=1015)
        self.assertEqual(self.d.showing[0], "amber")

    def test_alte_messungen_fallen_aus_dem_fenster(self):
        self.d.tick(now=1000)
        self.d.tick(now=1000 + b.DEFAULTS["window_s"] + 1)
        self.assertEqual(len(self.d.samples), 1)

    def test_laden_und_entladen_werden_nicht_gemischt(self):
        """The median is taken over readings of the same direction only -
        3 W in and 3 W out are opposite verdicts."""
        self.d.cfg["discharging"] = True
        self.d.tick(now=1000)                       # laedt mit 5.16 W: amber
        self.battery(status="Discharging", ampere=1.6, volt=3.9)   # 6.24 W
        self.d.tick(now=1100)
        # Als Ladeleistung waere das gruen, als Verbrauch ist es rot.
        self.assertEqual(self.d.showing[0], "red")

    def test_stecker_raus_nimmt_die_farbe_weg(self):
        self.d.tick(now=1000)
        self.battery(status="Discharging", ampere=0.5, volt=3.9)   # 1.95 W
        self.assertTrue(self.d.tick(now=1100))
        self.assertIsNone(self.d.showing[0])
        self.assertEqual(b.Setting().get(), "base")

    def test_voll_nimmt_die_farbe_weg(self):
        self.d.tick(now=1000)
        self.battery(status="Full", ampere=0.0, volt=4.4)
        self.assertTrue(self.d.tick(now=1100))
        self.assertEqual(b.Setting().get(), "base")

    def test_unlesbarer_akku_laesst_die_farbe_erst_stehen(self):
        """A single failed read must not restyle every app on the phone."""
        self.d.tick(now=1000)
        os.unlink(os.path.join(self.sysfs, "current_now"))
        self.assertFalse(self.d.tick(now=1030))
        self.assertEqual(self.d.showing[0], "amber")

    def test_und_nimmt_sie_weg_wenn_es_dabei_bleibt(self):
        """But a colour nothing can justify any more is worse than none."""
        self.d.tick(now=1000)
        os.unlink(os.path.join(self.sysfs, "current_now"))
        self.assertTrue(self.d.tick(now=1000 + b.DEFAULTS["window_s"] + 1))
        self.assertIsNone(self.d.showing[0])
        self.assertEqual(b.Setting().get(), "base")

    def test_neues_theme_des_nutzers_wird_uebernommen(self):
        self.d.tick(now=1000)
        self.make_theme("anderes")
        self.set_theme("anderes")
        self.d.tick(now=1100)
        self.assertEqual(self.d.base, "anderes")
        self.assertEqual(b.Setting().get(), b.theme_name("anderes", "amber"))
        # Written when it is needed, not all twelve up front: twelve
        # directories in ~/.themes are twelve entries in a theme chooser.
        self.assertTrue(os.path.isdir(os.path.join(self.themes,
                                                   b.theme_name("anderes", "amber"))))
        self.assertFalse(os.path.isdir(os.path.join(self.themes,
                                                    b.theme_name("anderes", "green"))))

    def test_eigene_farbe_gilt_nicht_als_neues_theme(self):
        self.d.tick(now=1000)
        self.assertFalse(self.d.adopt(b.theme_name("base", "green")))
        self.assertEqual(self.d.base, "base")

    def test_uebernimmt_eine_farbe_aus_einem_frueheren_lauf(self):
        """After a crash the theme is still green. A fresh daemon has to
        start from what is on screen, or dwell and hysteresis both count from
        a colour nobody is looking at."""
        self.set_theme(b.theme_name("base", "green"))
        d = b.Daemon(jetzt=b.theme_name("base", "green"))
        # 6.67 W: under the 7 W that buys green, inside the tenth that keeps
        # it. A daemon that did not adopt what is on screen would read this
        # as amber and restyle the whole phone for nothing.
        self.battery(ampere=1.55, volt=4.3)
        self.assertFalse(d.tick(now=1000))
        self.assertEqual(d.showing[0], "green")
        self.assertEqual(b.Setting().get(), b.theme_name("base", "green"))
        # And it really is hysteresis, not a colour that can never leave.
        self.battery(ampere=1.2, volt=4.3)          # 5.16 W
        self.assertTrue(d.tick(now=1100))
        self.assertEqual(d.showing[0], "amber")

    def test_ohne_brauchbares_theme_passiert_nichts(self):
        self.set_theme("gibt-es-nicht")
        d = b.Daemon(jetzt="gibt-es-nicht")
        self.assertFalse(b.can_theme(d.base))
        self.assertFalse(d.tick(now=1000))

    def test_farbe_ohne_theme_wird_nicht_gesetzt(self):
        """apply() builds the themes if they are missing - and gives up
        quietly when the base theme cannot carry them."""
        self.set_theme("gibt-es-nicht")
        d = b.Daemon(jetzt="gibt-es-nicht")
        self.assertFalse(d.apply(("green", None), now=1000))
        self.assertIsNone(d.showing[0])

    def test_farbe_mit_theme_wird_bei_bedarf_gebaut(self):
        d = b.Daemon(jetzt="base")
        self.assertTrue(d.apply(("green", None), now=1000))
        self.assertEqual(b.Setting().get(), b.theme_name("base", "green"))

    def test_geaenderte_konfiguration_wirkt_ohne_neustart(self):
        """The app writes the config file; a daemon that read it once would
        make its switch look broken until the next boot."""
        self.battery(status="Discharging", ampere=1.6, volt=3.9)   # 6.24 W
        self.assertFalse(self.d.tick(now=1000))     # entladen ist aus
        b.save_config(dict(b.DEFAULTS, discharging=True))
        self.assertTrue(self.d.tick(now=1100))
        self.assertEqual(self.d.showing[0], "red")

    def test_unveraenderte_konfiguration_wird_nicht_neu_gelesen(self):
        b.save_config(dict(b.DEFAULTS, charge_green_w=9.0))
        d = b.Daemon(jetzt="base")
        self.assertFalse(d.reload())
        self.assertEqual(d.cfg["charge_green_w"], 9.0)

    def test_geloeschte_konfiguration_faellt_auf_defaults_zurueck(self):
        b.save_config(dict(b.DEFAULTS, charge_green_w=9.0))
        d = b.Daemon(jetzt="base")
        os.unlink(b.CONFIG)
        self.assertTrue(d.reload())
        self.assertEqual(d.cfg["charge_green_w"], 7.0)

    def test_die_fuellung_schaltet_die_huelle_nicht_mit(self):
        """One theme carries both halves, so a level crossing 60 % is one
        switch - and it must not be read as a change of the shell."""
        self.battery(ampere=1.2, volt=4.3, percent=80)     # 5.16 W: amber
        self.d.tick(now=1000)
        self.assertEqual(self.d.showing, ("amber", None))
        self.battery(ampere=1.2, volt=4.3, percent=50)
        self.assertTrue(self.d.tick(now=1100))
        self.assertEqual(self.d.showing, ("amber", "amber"))
        self.assertEqual(b.Setting().get(),
                         b.theme_name("base", "amber", "amber"))

    def test_die_fuellung_faerbt_auch_ohne_huelle(self):
        """On battery with an ordinary drain the shell says nothing - the
        filling still says the battery is nearly empty.

        With the real battery-level-10-symbolic, which is one of the three
        discharge icons Adwaita DOES draw in two paths (it colours the
        remainder itself at that level). The other nine are a single shape;
        that case is the test below.
        """
        self.d.icon = "battery-level-10-symbolic"
        self.battery(status="Discharging", ampere=0.2, volt=3.9, percent=8)
        self.assertTrue(self.d.tick(now=1000))
        self.assertEqual(self.d.showing, (None, "red"))
        self.assertEqual(b.Setting().get(), b.theme_name("base", None, "red"))

    def test_ein_symbol_aus_einem_stueck_bekommt_eine_farbe(self):
        """The plain discharge icon is a single path, so colouring shell and
        filling differently would mean one of them silently overwriting the
        other. The more urgent one speaks for the whole icon."""
        self.d.icon = "battery-level-90-symbolic"
        self.d.cfg["discharging"] = True
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=90)
        self.d.tick(now=1000)              # 6.24 W: Huelle rot, Stand egal
        self.assertEqual(self.d.showing, ("red", "red"))

    def test_und_die_dringlichere_gewinnt(self):
        """Half full and drawing hard: the level would say amber, the drain
        says red, and one shape can only say one of them."""
        self.d.icon = "battery-level-50-symbolic"
        self.d.cfg["discharging"] = True
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=50)
        self.d.tick(now=1000)              # 6.24 W
        self.assertEqual(self.d.showing, ("red", "red"))

    def test_beim_laden_bleiben_es_zwei(self):
        self.d.icon = "battery-level-50-charging-symbolic"
        self.battery(ampere=1.2, volt=4.3, percent=50)   # 5.16 W: amber
        self.d.tick(now=1000)
        self.assertEqual(self.d.showing, ("amber", "amber"))
        self.battery(ampere=2.5, volt=4.3, percent=50)   # 10.75 W: green
        self.d.tick(now=1100)
        self.assertEqual(self.d.showing, ("green", "amber"))

    def test_der_lauf_faerbt_bei_widerspruch_nur_den_stand(self):
        self.d.icon = "battery-full-symbolic"      # kein Blitz
        self.battery(status="Charging", ampere=0.2, volt=4.3, percent=85)
        self.assertFalse(self.d.tick(now=1000))
        self.assertEqual(self.d.showing, (None, None))
        self.assertEqual(b.Setting().get(), "base")

    def test_eine_wackelnde_richtung_faerbt_die_huelle_nicht(self):
        """A worn USB port flips between charging and discharging every few
        minutes. Following that would restyle every GTK3 app about once a
        minute for something the cable is doing."""
        self.d.cfg["discharging"] = True
        self.battery(status="Charging", ampere=1.2, volt=4.3, percent=80)
        self.d.tick(now=1000)
        self.assertEqual(self.d.showing[0], "amber")
        # Stecker wackelt: noch im selben Fenster, andere Richtung.
        # 1050, nicht 1100: nach einer vollen Fensterlaenge waere die alte
        # Messung heraus und die Richtung waere wieder eindeutig - der Test
        # wuerde dann das Gegenteil pruefen.
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=80)
        self.assertTrue(self.d.tick(now=1050))
        self.assertIsNone(self.d.showing[0])

    def test_und_faerbt_wieder_wenn_sie_sich_beruhigt_hat(self):
        self.d.cfg["discharging"] = True
        self.battery(status="Charging", ampere=1.2, volt=4.3, percent=80)
        self.d.tick(now=1000)
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=80)
        self.d.tick(now=1050)
        self.assertIsNone(self.d.showing[0])
        # Ein ganzes Fenster lang nur noch die eine Richtung
        self.d.tick(now=1050 + b.DEFAULTS["window_s"] + 1)
        self.assertEqual(self.d.showing[0], "red")

    def test_der_ladestand_wackelt_nicht_mit(self):
        """The level is the same number whichever way the current is
        flowing, so it keeps its colour while the direction is unsettled."""
        self.d.icon = "battery-level-10-charging-symbolic"   # zwei Pfade
        self.battery(status="Charging", ampere=1.2, volt=4.3, percent=9)
        self.d.tick(now=1000)
        self.battery(status="Discharging", ampere=1.2, volt=3.9, percent=9)
        self.d.tick(now=1050)
        self.assertEqual(self.d.showing[1], "red")

    def test_setzen_kann_scheitern(self):
        class Stur(b.Setting):
            def set(self, name):
                return False
        d = b.Daemon(setting=Stur(self.setting), jetzt="base")
        self.assertFalse(d.tick(now=1000))
        self.assertIsNone(d.showing[0])


if __name__ == "__main__":
    # Built by hand rather than through unittest.main(), which looks for tests
    # in sys.modules["__main__"] - and under the coverage tracer that is the
    # tracer, not this file. It finds nothing there and says so quietly:
    # "Ran 0 tests", exit 0, and a coverage report of 16 %.
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for obj in list(globals().values()):
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
            suite.addTests(loader.loadTestsFromTestCase(obj))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
