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


class Base(unittest.TestCase):
    """A temporary phone: a battery directory, a themes directory, a config."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sysfs = os.path.join(self.tmp, "battery")
        self.themes = os.path.join(self.tmp, "themes")
        self.setting = os.path.join(self.tmp, "gtk-theme")
        os.makedirs(self.sysfs)
        os.makedirs(self.themes)
        # Every path that would otherwise point into the real home.
        # Complete, and that is not fussiness: the version without ICON_BASE
        # deleted the icons of the running phone during a test run and left a
        # broken icon in the bar (15.9.2026).
        self.old_paths = (b.SYSFS, b.CONFIG, b.THEMES, list(b.THEME_DIRS),
                    b.ICON_BASE, b.ICON_SOURCE, list(b.ICON_DIRS))
        self.alter_pfad = os.environ["PATH"]
        self.icon_root = os.path.join(self.tmp, "icons")
        b.ICON_BASE = self.icon_root
        b.ICON_DIRS[:] = [self.icon_root]
        self.icon_setting = os.path.join(self.tmp, "icon-theme")
        with open(self.icon_setting, "w") as fh:
            fh.write("Adwaita\n")
        os.environ["FURIOS_BATTERY_ICON_SETTING_FILE"] = self.icon_setting
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
        b.SYSFS, b.CONFIG, b.THEMES = self.old_paths[:3]
        b.THEME_DIRS[:] = self.old_paths[3]
        b.ICON_BASE, b.ICON_SOURCE = self.old_paths[4], self.old_paths[5]
        b.ICON_DIRS[:] = self.old_paths[6]
        os.environ.pop("FURIOS_BATTERY_ICON_SETTING_FILE", None)
        os.environ.pop("FURIOS_BATTERY_SETTING_FILE", None)
        os.environ.pop("FURIOS_BATTERY_ICON", None)
        os.environ["PATH"] = self.alter_pfad
        for folder, _, files in os.walk(self.tmp, topdown=False):
            for file_ in files:
                os.unlink(os.path.join(folder, file_))
            os.rmdir(folder)

    # -- Helfer ------------------------------------------------------------
    def battery(self, status="Charging", ampere=1.2, volt=4.3, percent=80):
        values = {"status": status,
                 "current_now": str(int(ampere * 1e6)),
                 "voltage_now": str(int(volt * 1e6)),
                 "capacity": str(percent)}
        for name, value in values.items():
            with open(os.path.join(self.sysfs, name), "w") as fh:
                fh.write(value + "\n")

    def set_theme(self, name):
        with open(self.setting, "w") as fh:
            fh.write(name + "\n")

    def alle_themes(self, base="base"):
        """The three power colours, as write_themes used to write them."""
        return [b.write_theme(base, colour, None) for colour in b.BUCKETS]

    def icon_with_bolt(self, name):
        """An icon in the search path whose bolt is a path of its own."""
        folder = os.path.join(self.icon_root, "Adwaita", "symbolic", "status")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name + ".svg"), "w") as fh:
            fh.write('<svg>%s<path class="warning" d="M 13 8"/>'
                     '<path class="success" d="m 5 7"/>'
                     '<path d="m 7 0"/></svg>' % b.BOLT_MARK)

    def icon_with_two_areas(self, name):
        """An icon in the search path that has a filling area of its own."""
        folder = os.path.join(self.icon_root, "Adwaita", "symbolic", "status")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name + ".svg"), "w") as fh:
            fh.write('<svg><path class="success" d="m 5 7"/>'
                     '<path d="m 7 0"/></svg>')

    def make_theme(self, name, dark=True):
        gtk3 = os.path.join(self.themes, name, "gtk-3.0")
        os.makedirs(gtk3, exist_ok=True)
        with open(os.path.join(gtk3, "gtk.css"), "w") as fh:
            fh.write("/* the user's own */\n")
        if dark:
            with open(os.path.join(gtk3, "gtk-dark.css"), "w") as fh:
                fh.write("/* the user's own, dark */\n")

    def run_cmd(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = b.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class Reading(Base):
    def test_reads_watts(self):
        self.battery(ampere=1.2, volt=4.3)
        reading = b.read_battery()
        self.assertAlmostEqual(reading["watt"], 5.16, places=2)
        self.assertTrue(reading["charging"])
        self.assertTrue(reading["moving"])

    def test_a_missing_file_is_none(self):
        self.assertIsNone(b.read_battery())

    def test_an_unreadable_value_is_none(self):
        self.battery()
        with open(os.path.join(self.sysfs, "current_now"), "w") as fh:
            fh.write("keine zahl\n")
        self.assertIsNone(b.read_battery())

    def test_the_sign_is_thrown_away(self):
        """Some drivers count discharge negative. Direction comes from
        `status`, never from the sign, or a discharging phone would read as
        -3 W and land in a bucket by arithmetic accident."""
        self.battery(status="Discharging", ampere=-0.8, volt=3.9)
        reading = b.read_battery()
        self.assertAlmostEqual(reading["watt"], 3.12, places=2)
        self.assertFalse(reading["charging"])
        self.assertTrue(reading["moving"])

    def test_full_is_not_moving(self):
        self.battery(status="Full", ampere=0.0, volt=4.4)
        self.assertFalse(b.read_battery()["moving"])

    def test_not_charging_is_not_moving(self):
        self.battery(status="Not charging", ampere=0.0, volt=4.4)
        self.assertFalse(b.read_battery()["moving"])

    def test_an_implausible_reading_is_recognised(self):
        """A driver reporting milliamps where the class says microamps would
        make every charge look like a thousand watts - and the icon
        permanently green."""
        self.battery(ampere=1200.0, volt=4.3)
        self.assertFalse(b.read_battery()["plausible"])

    def test_median(self):
        self.assertEqual(b.median([3, 1, 2]), 2)
        self.assertEqual(b.median([4, 1, 2, 3]), 2.5)
        self.assertIsNone(b.median([]))


class Thresholds(Base):
    def setUp(self):
        super().setUp()
        self.cfg = dict(b.DEFAULTS)

    def test_charging_has_three_steps(self):
        self.assertEqual(b.bucket_for(8.0, True, self.cfg), "green")
        self.assertEqual(b.bucket_for(5.0, True, self.cfg), "amber")
        self.assertEqual(b.bucket_for(1.0, True, self.cfg), "red")

    def test_exactly_on_the_threshold_is_the_better_colour(self):
        self.assertEqual(b.bucket_for(7.0, True, self.cfg), "green")
        self.assertEqual(b.bucket_for(3.0, True, self.cfg), "amber")

    def test_on_battery_it_normally_stays_plain(self):
        """White is the normal state on battery: a phone doing what a phone
        does says nothing, and only an unusual drain speaks up."""
        self.assertIsNone(b.bucket_for(0.2, False, self.cfg))
        self.assertIsNone(b.bucket_for(2.0, False, self.cfg))
        self.assertEqual(b.bucket_for(3.5, False, self.cfg), "amber")
        self.assertEqual(b.bucket_for(9.0, False, self.cfg), "red")

    def test_on_battery_there_is_no_green(self):
        """Green on battery would be a colour on all day - no signal at
        all."""
        for watt in (0.0, 0.5, 1.0, 2.9, 3.5, 12.0):
            self.assertNotEqual(b.bucket_for(watt, False, self.cfg), "green")

    def test_hysteresis_holds_green(self):
        """6.5 W is under the 7 W it took to go green, but not far enough
        under to give it up - the reading swings that much on its own."""
        self.assertEqual(b.bucket_for(6.5, True, self.cfg, "green"), "green")
        self.assertEqual(b.bucket_for(6.2, True, self.cfg, "green"), "amber")

    def test_hysteresis_holds_red(self):
        self.assertEqual(b.bucket_for(3.2, True, self.cfg, "red"), "red")
        self.assertEqual(b.bucket_for(3.4, True, self.cfg, "red"), "amber")

    def test_leaving_amber_costs_more(self):
        self.assertEqual(b.bucket_for(7.5, True, self.cfg, "amber"), "amber")
        self.assertEqual(b.bucket_for(7.8, True, self.cfg, "amber"), "green")

    def test_leaving_plain_costs_a_tenth_more(self):
        """Otherwise the icon would light up on the noise of a reading that
        sits on the threshold."""
        self.assertIsNone(b.bucket_for(3.2, False, self.cfg, None))
        self.assertEqual(b.bucket_for(3.4, False, self.cfg, None), "amber")

    def test_hysteresis_on_battery_from_amber_and_red(self):
        # out of amber, downwards and upwards
        self.assertEqual(b.bucket_for(2.8, False, self.cfg, "amber"), "amber")
        self.assertIsNone(b.bucket_for(2.6, False, self.cfg, "amber"))
        self.assertEqual(b.bucket_for(5.4, False, self.cfg, "amber"), "amber")
        self.assertEqual(b.bucket_for(5.6, False, self.cfg, "amber"), "red")
        # and out of red
        self.assertEqual(b.bucket_for(4.6, False, self.cfg, "red"), "red")
        self.assertEqual(b.bucket_for(4.4, False, self.cfg, "red"), "amber")
        self.assertIsNone(b.bucket_for(1.0, False, self.cfg, "red"))

    def test_switched_off_means_no_colour(self):
        self.battery()
        cfg = dict(self.cfg, charging=False)
        self.assertIsNone(b.wanted_bucket(b.read_battery(), cfg))

    def test_on_battery_only_when_wanted(self):
        self.battery(status="Discharging", ampere=1.5, volt=3.9)   # 5.85 W
        reading = b.read_battery()
        self.assertIsNone(b.wanted_bucket(reading, self.cfg))
        self.assertEqual(b.wanted_bucket(reading, dict(self.cfg, discharging=True)),
                         "red")

    def test_an_ordinary_drain_colours_nothing_even_then(self):
        """The option is "say something when it is unusual", not "be
        coloured whenever the cable is out"."""
        self.battery(status="Discharging", ampere=0.2, volt=3.9)   # 0.78 W
        self.assertIsNone(b.wanted_bucket(b.read_battery(),
                                          dict(self.cfg, discharging=True)))

    def test_full_gets_no_colour(self):
        self.battery(status="Full", ampere=0.0, volt=4.4)
        self.assertIsNone(b.wanted_bucket(b.read_battery(), self.cfg))

    def test_unreadable_gets_no_colour(self):
        self.assertIsNone(b.wanted_bucket(None, self.cfg))

    def test_implausible_gets_no_colour(self):
        self.battery(ampere=900.0, volt=4.3)
        self.assertIsNone(b.wanted_bucket(b.read_battery(), self.cfg))


class FillLevel(Base):
    """The filling says something else than the shell: how full, not how
    fast."""

    def setUp(self):
        super().setUp()
        self.cfg = dict(b.DEFAULTS)

    def test_three_bands(self):
        self.assertIsNone(b.level_for(85, self.cfg))
        self.assertIsNone(b.level_for(61, self.cfg))
        self.assertEqual(b.level_for(59, self.cfg), "amber")
        self.assertEqual(b.level_for(16, self.cfg), "amber")
        self.assertEqual(b.level_for(14, self.cfg), "red")
        self.assertEqual(b.level_for(0, self.cfg), "red")

    def test_the_boundary_itself_belongs_to_the_better_colour(self):
        self.assertIsNone(b.level_for(60, self.cfg))
        self.assertEqual(b.level_for(15, self.cfg), "amber")

    def test_hysteresis_of_two_points(self):
        """A percentage stepping across 60 and back must not restyle every
        app twice a minute."""
        self.assertEqual(b.level_for(61, self.cfg, "amber"), "amber")
        self.assertIsNone(b.level_for(63, self.cfg, "amber"))
        self.assertEqual(b.level_for(14, self.cfg, "red"), "red")
        self.assertEqual(b.level_for(16, self.cfg, "red"), "red")
        self.assertEqual(b.level_for(18, self.cfg, "red"), "amber")

    def test_an_unreadable_level_colours_nothing(self):
        """Not "nearly empty": a phone whose capacity cannot be read must
        not have its icon painted as a warning."""
        self.assertIsNone(b.level_for(None, self.cfg))

    def test_can_be_switched_off(self):
        self.assertIsNone(b.level_for(5, dict(self.cfg, level=False)))

    def test_from_the_reading(self):
        self.battery(percent=42)
        self.assertEqual(b.wanted_level(b.read_battery(), self.cfg), "amber")
        self.assertIsNone(b.wanted_level(None, self.cfg))

    def test_a_missing_capacity_file(self):
        self.battery()
        os.unlink(os.path.join(self.sysfs, "capacity"))
        self.assertIsNone(b.read_battery()["percent"])

    def test_the_filling_does_not_depend_on_the_direction(self):
        """Independent of the shell on purpose: a nearly empty battery says
        so whether it is charging, draining or full."""
        for state in ("Charging", "Discharging", "Full", "Not charging"):
            self.battery(status=state, percent=9)
            self.assertEqual(b.wanted_level(b.read_battery(), self.cfg), "red",
                             state)


class IconFamilies(Base):
    """Which icon is on screen decides whether there are two halves to
    colour."""

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
        path = os.path.join(self.icons, name + ".svg")
        with open(path, "w") as fh:
            fh.write('<svg>%s<path d="m 0 0"/></svg>'
                     % ('<path class="success" d="m 5 7"/>' if mit_klasse else ""))
        return path

    def test_two_paths_can_be_coloured_separately(self):
        self.icon("battery-level-90-charging-symbolic", True)
        self.assertTrue(b.icon_is_split("battery-level-90-charging-symbolic"))

    def test_one_path_cannot(self):
        """Adwaita's twelve discharge icons are ONE path: `color` colours the
        whole icon and the palette colours nothing."""
        self.icon("battery-level-90-symbolic", False)
        self.assertFalse(b.icon_is_split("battery-level-90-symbolic"))

    def test_the_file_decides_not_the_name(self):
        """An icon theme may build everything differently - the file is read,
        and only guessed at when there is none."""
        self.icon("battery-full-charging-symbolic", False)
        self.assertFalse(b.icon_is_split("battery-full-charging-symbolic"))

    def test_without_a_file_the_name_decides(self):
        self.assertTrue(b.icon_is_split("battery-level-40-charging-symbolic"))
        self.assertTrue(b.icon_is_split("battery-level-40-plugged-in-symbolic"))
        self.assertFalse(b.icon_is_split("battery-level-40-symbolic"))

    def test_without_a_name_the_direction_decides(self):
        self.assertTrue(b.icon_is_split(None, charging=True))
        self.assertFalse(b.icon_is_split(None, charging=False))
        self.assertIsNone(b.find_icon(None))

    def test_contradicting_sources_leave_the_shell_plain(self):
        """Seen on the phone: sysfs "Charging" at 1.8 W, UPower
        "discharging" at 0 W, and phosh drawing the icon without a bolt. A
        charging colour on that icon answers a question the picture does
        not ask."""
        self.battery(status="Charging", ampere=0.2, volt=4.3)
        reading = b.read_battery()
        cfg = dict(b.DEFAULTS)
        self.assertEqual(b.wanted_bucket(reading, cfg), "red")
        self.assertEqual(
            b.wanted_bucket(reading, cfg, icon="battery-level-90-charging-symbolic"),
            "red")
        self.assertIsNone(
            b.wanted_bucket(reading, cfg, icon="battery-full-symbolic"))

    def test_agreement_without_an_icon_and_without_a_reading(self):
        self.battery()
        self.assertTrue(b.sources_agree(b.read_battery(), None))
        self.assertTrue(b.sources_agree(None, "battery-full-symbolic"))

    def test_the_level_stays_untouched_by_that(self):
        """How full it is, both sources agree on."""
        self.battery(status="Charging", ampere=0.2, volt=4.3, percent=9)
        self.assertEqual(b.wanted_level(b.read_battery(), dict(b.DEFAULTS)),
                         "red")

    def test_the_name_phosh_draws(self):
        """Nicht UPowers `icon-name`: phosh baut
        "battery-level-%d-symbolic" itself, and the two files are not even
        built the same way."""
        self.assertEqual(b.phosh_icon(87, False), "battery-level-90-symbolic")
        self.assertEqual(b.phosh_icon(87, True),
                         "battery-level-90-charging-symbolic")
        self.assertEqual(b.phosh_icon(4, False), "battery-level-0-symbolic")
        self.assertEqual(b.phosh_icon(100, False), "battery-level-100-symbolic")
        # Out of range and unknown, neither of them a crash
        self.assertEqual(b.phosh_icon(140, False), "battery-level-100-symbolic")
        self.assertEqual(b.phosh_icon(None, False), "battery-level-100-symbolic")

    def test_one_shape_gets_the_more_urgent_colour(self):
        self.assertEqual(b.merge_colours("green", "red"), "red")
        self.assertEqual(b.merge_colours("red", "amber"), "red")
        self.assertEqual(b.merge_colours(None, "amber"), "amber")
        self.assertEqual(b.merge_colours("green", None), "green")
        self.assertIsNone(b.merge_colours(None, None))

    def test_there_is_exactly_one_seam_for_the_tests(self):
        os.environ["FURIOS_BATTERY_ICON"] = "battery-full-symbolic"
        self.assertEqual(b.upower_icon(), "battery-full-symbolic")
        os.environ["FURIOS_BATTERY_ICON"] = ""
        self.assertIsNone(b.upower_icon())

    def test_upower_is_asked_because_phosh_asks_it_too(self):
        os.environ.pop("FURIOS_BATTERY_ICON", None)
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        with open(os.path.join(bin_dir, "upower"), "w") as fh:
            fh.write("#!/bin/sh\necho \"  icon-name: 'battery-full-symbolic'\"\n")
        os.chmod(os.path.join(bin_dir, "upower"), 0o755)
        os.environ["PATH"] = bin_dir + ":" + os.environ["PATH"]
        self.assertEqual(b.upower_icon(), "battery-full-symbolic")

    def test_without_upower_it_does_not_crash(self):
        os.environ.pop("FURIOS_BATTERY_ICON", None)
        os.environ["PATH"] = os.path.join(self.tmp, "empty")
        self.assertIsNone(b.upower_icon())


class OwnIconTheme(Base):
    """Our own icon theme - Adwaita inherited, plus discharge icons with a
    filling area that can be coloured on its own."""

    def setUp(self):
        super().setUp()
        self.source = os.path.join(self.tmp, "adwaita")
        os.makedirs(self.source)
        b.ICON_SOURCE = self.source

    def original(self, level, klasse=False):
        path = os.path.join(self.source, "battery-level-%d-symbolic.svg" % level)
        with open(path, "w") as fh:
            fh.write('<svg height="16px" width="16px">\n'
                     + ('<path class="success" d="m 5 7"/>\n' if klasse else "")
                     + '<path d="m 7 0 c -1 0"/>\n</svg>')
        return path

    def files(self):
        return sorted(os.listdir(os.path.join(
            b.icon_theme_dir(), "symbolic", "status")))

    def test_the_filling_area_is_added(self):
        self.original(90)
        names = b.write_icon_theme("Adwaita")
        self.assertEqual(names, ["battery-level-90-symbolic.svg"])
        text = open(os.path.join(b.icon_theme_dir(), "symbolic", "status",
                                 names[0])).read()
        self.assertIn('class="success"', text)
        # 90 % is seven of eight units, resting on 13 at the bottom
        self.assertIn('d="m 5 6 h 6 v 7 h -6 z"', text)
        self.assertIn("battctl", text)

    def test_the_geometry_is_right_per_level(self):
        for level, expected in ((100, "m 5 5 h 6 v 8 h -6 z"),
                                (50, "m 5 9 h 6 v 4 h -6 z"),
                                (30, "m 5 11 h 6 v 2 h -6 z")):
            self.original(level)
            b.write_icon_theme("Adwaita")
            text = open(os.path.join(b.icon_theme_dir(), "symbolic", "status",
                                     "battery-level-%d-symbolic.svg" % level)).read()
            self.assertIn(expected, text, level)

    def test_the_theme_inherits_the_users_own(self):
        self.original(90)
        b.write_icon_theme("Papirus")
        index = open(os.path.join(b.icon_theme_dir(), "index.theme")).read()
        self.assertIn("Inherits=Papirus,hicolor", index)
        self.assertEqual(b.icon_base_theme(), "Papirus")

    def test_no_icons_no_index(self):
        """A theme with no files would be one that only changes the setting
        and can do nothing."""
        self.assertEqual(b.write_icon_theme("Adwaita"), [])
        self.assertFalse(os.path.exists(os.path.join(b.icon_theme_dir(),
                                                     "index.theme")))
        self.assertIsNone(b.icon_base_theme())

    def test_what_already_has_two_areas_stays_untouched(self):
        self.original(20, klasse=True)
        self.assertEqual(b.write_icon_theme("Adwaita"), [])

    def test_an_empty_battery_has_nothing_to_colour(self):
        self.original(0)
        self.assertEqual(b.write_icon_theme("Adwaita"), [])

    def test_writing_twice_changes_nothing(self):
        self.original(90)
        b.write_icon_theme("Adwaita")
        path = os.path.join(b.icon_theme_dir(), "symbolic", "status",
                            "battery-level-90-symbolic.svg")
        before = os.stat(path).st_mtime_ns
        b.write_icon_theme("Adwaita")
        self.assertEqual(before, os.stat(path).st_mtime_ns)

    def test_a_missing_source_does_not_crash(self):
        b.ICON_SOURCE = os.path.join(self.tmp, "does-not-exist")
        self.assertEqual(b.write_icon_theme("Adwaita"), [])
        self.assertIsNone(b.split_icon_svg("/does/not/exist", 50))

    def test_switching_on_sets_the_setting(self):
        self.original(90)
        self.assertTrue(b.use_icon_theme())
        self.assertEqual(b.icon_setting().get(), b.ICON_THEME)

    def test_and_remembers_the_users_own_theme(self):
        self.original(90)
        with open(self.icon_setting, "w") as fh:
            fh.write("Papirus\n")
        b.use_icon_theme()
        self.assertEqual(b.icon_base_theme(), "Papirus")
        # A second run must not overwrite it with our own name - the way
        # back would be gone.
        b.use_icon_theme()
        self.assertEqual(b.icon_base_theme(), "Papirus")

    def test_without_usable_icons_nothing_is_switched(self):
        self.assertFalse(b.use_icon_theme())
        self.assertEqual(b.icon_setting().get(), "Adwaita")

    def test_back_means_the_setting_first_then_the_files(self):
        """In dieser Reihenfolge: ein Thema, dessen Dateien unter einer
        shell that has them cached leaves a broken icon in the bar - seen
        on the device."""
        self.original(90)
        b.use_icon_theme()
        self.assertEqual(b.drop_icon_theme(), 1)
        self.assertEqual(b.icon_setting().get(), "Adwaita")
        self.assertFalse(os.path.exists(b.icon_theme_dir()))

    def test_a_foreign_directory_of_the_same_name_stays(self):
        folder = os.path.join(b.icon_theme_dir(), "symbolic", "status")
        os.makedirs(folder)
        with open(os.path.join(folder, "battery-level-90-symbolic.svg"), "w") as fh:
            fh.write("<svg>somebody else's</svg>")
        self.assertEqual(b.drop_icon_theme(), 0)
        self.assertTrue(os.path.exists(folder))

    def test_afterwards_the_icon_counts_as_split(self):
        """The point of the whole exercise: from now on the discharge icon
        has two areas."""
        self.original(90)
        b.write_icon_theme("Adwaita")
        self.assertTrue(b.icon_is_split("battery-level-90-symbolic"))


class Names(Base):
    def test_our_own_theme_is_recognised(self):
        self.assertEqual(b.base_name(b.theme_name("adw-gtk3", "green")),
                         "adw-gtk3")
        # And the ones an older version of the rule wrote, with a different
        # token or none at all - otherwise an upgrade would take somebody's
        # own theme to be "adw-gtk3-batt-green".
        self.assertEqual(b.base_name("adw-gtk3-batt-red"), "adw-gtk3")
        self.assertEqual(b.base_name("adw-gtk3-batt9f9f-red"), "adw-gtk3")

    def test_a_foreign_theme_stays(self):
        self.assertEqual(b.base_name("adw-gtk3"), "adw-gtk3")
        self.assertEqual(b.base_name("Yaru-batt-blue"), "Yaru-batt-blue")
        self.assertEqual(b.base_name("batt-green"), "batt-green")
        self.assertEqual(b.base_name(""), "")

    def test_building_a_name(self):
        self.assertEqual(b.theme_name("adw-gtk3", "amber"),
                         "adw-gtk3-batt%s-amber-none-d" % b.TOKEN)
        self.assertEqual(b.theme_name("adw-gtk3", None, "red"),
                         "adw-gtk3-batt%s-none-red-d" % b.TOKEN)
        # The third part says which shape the power colour lands on.
        self.assertEqual(b.theme_name("adw-gtk3", "red", "amber", "c"),
                         "adw-gtk3-batt%s-red-amber-c" % b.TOKEN)
        # Both halves are independent, and the name says both.
        self.assertEqual(b.colours_of(b.theme_name("adw-gtk3", "green", "red")),
                         ("green", "red"))
        self.assertEqual(b.colours_of(b.theme_name("adw-gtk3", None, "amber")),
                         (None, "amber"))
        self.assertEqual(b.colours_of("adw-gtk3"), ("", ""))

    def test_there_and_back(self):
        for base in ("adw-gtk3", "Adwaita", "a-b-c"):
            for bucket in b.BUCKETS:
                self.assertEqual(b.base_name(b.theme_name(base, bucket)), base)


class Themes(Base):
    def test_writes_three(self):
        self.make_theme("base")
        names = self.alle_themes()
        self.assertEqual(len(names), 3)
        for name in names:
            path = os.path.join(self.themes, name, "gtk-3.0", "gtk.css")
            body = open(path).read()
            self.assertIn("phosh-battery-info image", body)
            self.assertIn("@import", body)

    def test_the_colours_are_right(self):
        self.make_theme("base")
        self.alle_themes()
        for bucket, colour in b.COLORS.items():
            path = os.path.join(self.themes, b.theme_name("base", bucket),
                                "gtk-3.0", "gtk.css")
            self.assertIn(colour, open(path).read())

    def test_both_halves_stand_apart_in_the_rule(self):
        """The icon is two paths and now says two things: the shell follows
        `color` (how fast), the filling comes from the symbolic palette (how
        full). Colouring only the first left a white filling in a red
        battery - which is what the phone showed on 15.9.2026."""
        self.make_theme("base")
        b.write_theme("base", "red", "amber")
        body = open(os.path.join(self.themes,
                                   b.theme_name("base", "red", "amber"),
                                   "gtk-3.0", "gtk.css")).read()
        self.assertIn("color: %s;" % b.COLORS["red"], body)
        # success AND error, because the low-level icons draw their filling
        # with the second one. warning belongs to the bolt and must not
        # take the filling colour - an 84 %% battery went orange that way.
        for name in ("success", "error"):
            self.assertIn("%s %s" % (name, b.COLORS["amber"]), body)
        self.assertNotIn("warning", body)

    def test_what_says_nothing_is_not_written(self):
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

    def test_without_either_there_is_no_theme(self):
        self.make_theme("base")
        self.assertEqual(b.css_rule(None, None), "")
        self.assertIsNone(b.write_theme("base", None, None))

    def test_the_rule_is_valid_gtk3_css(self):
        """Checked against GTK itself rather than by reading it: an unknown
        property is dropped with a warning nobody sees, and the icon would
        simply stay half-coloured."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk
        except (ImportError, ValueError):                 # pragma: no cover
            self.skipTest("no GTK3")
        self.make_theme("base")
        self.alle_themes()
        path = os.path.join(self.themes, b.theme_name("base", "green"), "gtk-3.0",
                            "gtk.css")
        text = open(path).read().split("*/", 1)[1]        # without the @import
        error = []
        prov = Gtk.CssProvider()
        prov.connect("parsing-error", lambda p, s, e: error.append(e.message))
        prov.load_from_data(text.encode())
        self.assertEqual([], error)

    def test_no_dark_sheet_is_invented(self):
        """The trap that would change the whole look of the phone: GTK3 uses
        gtk-dark.css when it exists. Writing one for a theme that has none
        would put the LIGHT stylesheet behind dark mode."""
        self.make_theme("base", dark=False)
        self.alle_themes()
        path = os.path.join(self.themes, b.theme_name("base", "green"), "gtk-3.0",
                            "gtk-dark.css")
        self.assertFalse(os.path.exists(path))

    def test_the_dark_sheet_disappears_again(self):
        self.make_theme("base", dark=True)
        self.alle_themes()
        path = os.path.join(self.themes, b.theme_name("base", "green"), "gtk-3.0",
                            "gtk-dark.css")
        self.assertTrue(os.path.exists(path))
        self.make_theme("base", dark=False)
        os.unlink(os.path.join(self.themes, "base", "gtk-3.0", "gtk-dark.css"))
        self.alle_themes()
        self.assertFalse(os.path.exists(path))

    def test_the_built_in_adwaita(self):
        light, dark = b.base_css("Adwaita")
        self.assertTrue(light.startswith("resource:"))
        self.assertTrue(dark.endswith("gtk-contained-dark.css"))

    def test_an_unknown_theme_is_refused(self):
        self.assertEqual(b.base_css("does-not-exist"), (None, None))
        self.assertIsNone(b.write_theme("does-not-exist", "green", None))
        self.assertFalse(b.can_theme("does-not-exist"))

    def test_the_import_points_at_the_original(self):
        """@import, not a copy: everything the base theme loads by relative
        path has to keep resolving against where IT lives."""
        self.make_theme("base")
        self.alle_themes()
        body = open(os.path.join(self.themes, b.theme_name("base", "red"),
                                   "gtk-3.0", "gtk.css")).read()
        self.assertIn("file://" + os.path.join(self.themes, "base",
                                               "gtk-3.0", "gtk.css"), body)

    def test_removing_takes_only_ours(self):
        self.make_theme("base")
        self.alle_themes()
        # Somebody else's theme that happens to fit the pattern.
        self.make_theme("fremd-batt-green")
        gone = b.remove_themes()
        self.assertEqual(gone, 3)
        self.assertTrue(os.path.isdir(os.path.join(self.themes, "base")))
        self.assertTrue(os.path.isdir(os.path.join(self.themes,
                                                   "fremd-batt-green")))

    def test_old_generations_are_recognised_and_only_those(self):
        """An upgrade must clear out what the old rule wrote without
        touching what is in use - the names differ by the token, which is
        the whole reason it is in the name."""
        self.make_theme("base")
        aktuell = self.alle_themes()
        # What an older version would have left behind:
        for alt_name in ("base-batt-green", "base-batt9f9f-red-none"):
            gtk3 = os.path.join(self.themes, alt_name, "gtk-3.0")
            os.makedirs(gtk3)
            with open(os.path.join(gtk3, "gtk.css"), "w") as fh:
                fh.write("/* battctl */\n")
        stale = b.stale_themes()
        self.assertEqual(sorted(stale),
                         ["base-batt-green", "base-batt9f9f-red-none"])
        self.assertEqual(b.remove_themes(only=stale), 2)
        for name in aktuell:
            self.assertTrue(os.path.isdir(os.path.join(self.themes, name)), name)
        self.assertTrue(os.path.isdir(os.path.join(self.themes, "base")))

    def test_without_a_directory_there_is_nothing_stale(self):
        b.THEMES = os.path.join(self.tmp, "does-not-exist")
        b.THEME_DIRS[:] = [b.THEMES]
        self.assertEqual(b.stale_themes(), [])

    def test_removing_without_a_directory(self):
        b.THEMES = os.path.join(self.tmp, "does-not-exist")
        self.assertEqual(b.remove_themes(), 0)

    def test_removing_skips_what_it_cannot_read(self):
        """A directory that fits the name but holds no stylesheet of ours is
        not ours to delete."""
        os.makedirs(os.path.join(self.themes, b.theme_name("base", "green"), "gtk-3.0"))
        self.assertEqual(b.remove_themes(), 0)
        self.assertTrue(os.path.isdir(os.path.join(self.themes,
                                                   b.theme_name("base", "green"))))

    def test_a_built_in_theme_is_imported_by_resource(self):
        """Adwaita has no files on disk - GTK3 carries it as a resource, and
        the import has to say so rather than pointing at a path."""
        names = self.alle_themes("Adwaita")
        self.assertEqual(len(names), 3)
        body = open(os.path.join(self.themes, b.theme_name("Adwaita", "green"),
                                   "gtk-3.0", "gtk.css")).read()
        self.assertIn('@import url("resource:///org/gtk/libgtk/theme/Adwaita/',
                      body)
        self.assertNotIn("file://", body)


class TheSetting(Base):
    def test_reading_and_writing(self):
        s = b.Setting()
        self.assertEqual(s.get(), "base")
        self.assertTrue(s.set(b.theme_name("base", "green")))
        self.assertEqual(s.get(), b.theme_name("base", "green"))

    def test_a_missing_file_is_empty(self):
        os.unlink(self.setting)
        self.assertEqual(b.Setting().get(), "")

    def _fake_gsettings(self, rc=0, ausgabe="'adw-gtk3'"):
        """A gsettings on PATH, so the path the phone really takes is tested
        and not only the file the tests use."""
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        path = os.path.join(bin_dir, "gsettings")
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\n"
                     'if [ "$1" = get ]; then echo "%s"; fi\n'
                     "echo \"$@\" >> %s/aufrufe\n"
                     "exit %d\n" % (ausgabe, self.tmp, rc))
        os.chmod(path, 0o755)
        os.environ.pop("FURIOS_BATTERY_SETTING_FILE", None)
        os.environ["PATH"] = bin_dir + ":" + os.environ["PATH"]
        return os.path.join(self.tmp, "aufrufe")

    def test_the_real_gsettings_reads_and_writes(self):
        aufrufe = self._fake_gsettings()
        s = b.Setting()
        self.assertEqual(s.get(), "adw-gtk3")
        self.assertTrue(s.set("adw-gtk3-batt-green"))
        rows = open(aufrufe).read()
        self.assertIn("get org.gnome.desktop.interface gtk-theme", rows)
        self.assertIn("set org.gnome.desktop.interface gtk-theme "
                      "adw-gtk3-batt-green", rows)

    def test_a_failed_gsettings_says_so(self):
        self._fake_gsettings(rc=3)
        self.assertFalse(b.Setting().set("egal"))

    def test_a_missing_gsettings_does_not_crash(self):
        bin_dir = os.path.join(self.tmp, "empty")
        os.makedirs(bin_dir, exist_ok=True)
        os.environ.pop("FURIOS_BATTERY_SETTING_FILE", None)
        os.environ["PATH"] = bin_dir
        s = b.Setting()
        self.assertEqual(s.get(), "")
        self.assertFalse(s.set("egal"))


class Config(Base):
    def test_defaults_without_a_file(self):
        self.assertEqual(b.load_config(), b.DEFAULTS)

    def test_saving_and_reading(self):
        cfg = dict(b.DEFAULTS, discharging=True, charge_green_w=9.5)
        b.save_config(cfg)
        self.assertEqual(b.load_config()["charge_green_w"], 9.5)
        self.assertTrue(b.load_config()["discharging"])

    def test_a_broken_file_gives_defaults(self):
        with open(b.CONFIG, "w") as fh:
            fh.write("{ this is not json")
        self.assertEqual(b.load_config(), b.DEFAULTS)

    def test_foreign_keys_are_ignored(self):
        with open(b.CONFIG, "w") as fh:
            json.dump({"charge_green_w": 8.0, "unsinn": 1}, fh)
        cfg = b.load_config()
        self.assertEqual(cfg["charge_green_w"], 8.0)
        self.assertNotIn("unsinn", cfg)

    def test_a_wrong_type_is_ignored(self):
        with open(b.CONFIG, "w") as fh:
            json.dump({"charge_green_w": "viel"}, fh)
        self.assertEqual(b.load_config()["charge_green_w"],
                         b.DEFAULTS["charge_green_w"])

    def test_an_integer_counts_as_a_float(self):
        with open(b.CONFIG, "w") as fh:
            json.dump({"charge_green_w": 8}, fh)
        self.assertEqual(b.load_config()["charge_green_w"], 8.0)

    def test_a_list_instead_of_an_object(self):
        with open(b.CONFIG, "w") as fh:
            json.dump([1, 2], fh)
        self.assertEqual(b.load_config(), b.DEFAULTS)


class Commands(Base):
    def test_help_(self):
        for arg in ([], ["--help"], ["help"]):
            rc, out, _ = self.run_cmd(*arg)
            self.assertEqual(rc, 0)
            self.assertIn("battctl status", out)

    def test_an_unknown_command(self):
        rc, _, err = self.run_cmd("fliegen")
        self.assertEqual(rc, 2)
        self.assertIn("Unknown command", err)

    def test_status_readable(self):
        self.battery(ampere=1.9, volt=4.2)
        self.make_theme("base")
        rc, out, _ = self.run_cmd("status")
        self.assertEqual(rc, 0)
        self.assertIn("state:        Charging", out)
        self.assertIn("7.98 W", out)

    def test_status_without_a_battery(self):
        rc, out, _ = self.run_cmd("status")
        self.assertEqual(rc, 1)
        self.assertIn("not readable", out)

    def test_status_json(self):
        self.battery(ampere=1.9, volt=4.2)
        self.make_theme("base")
        rc, out, _ = self.run_cmd("status", "--json")
        daten = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(daten["bucket"], "green")
        self.assertEqual(daten["base_theme"], "base")
        self.assertEqual(daten["showing"], "none")
        self.assertTrue(daten["can_theme"])

    def test_status_reports_an_unusable_theme(self):
        self.battery()
        rc, out, _ = self.run_cmd("status")
        self.assertIn("no GTK3 stylesheet", out)
        self.assertEqual(rc, 0)

    def test_status_knows_the_running_colour(self):
        self.battery(ampere=0.2, volt=4.2)
        self.make_theme("base")
        self.set_theme(b.theme_name("base", "green"))
        _, out, _ = self.run_cmd("status")
        self.assertIn("frame:        green", out)
        self.assertIn("base theme:   base", out)

    def test_config_shows_everything(self):
        rc, out, _ = self.run_cmd("config")
        self.assertEqual(rc, 0)
        self.assertIn("charge_green_w: 7.0", out)

    def test_config_switches(self):
        rc, out, _ = self.run_cmd("config", "discharging", "on")
        self.assertEqual(rc, 0)
        self.assertIn("discharging: True", out)
        self.assertTrue(b.load_config()["discharging"])

    def test_config_takes_hyphens(self):
        rc, _, _ = self.run_cmd("config", "charge-green-w", "9")
        self.assertEqual(rc, 0)
        self.assertEqual(b.load_config()["charge_green_w"], 9.0)

    def test_config_keeps_an_integer_an_integer(self):
        self.run_cmd("config", "dwell_s", "90")
        self.assertIsInstance(b.load_config()["dwell_s"], int)

    def test_config_refuses_nonsense(self):
        for argv in (("config", "discharging", "vielleicht"),
                     ("config", "charge_green_w", "viel"),
                     ("config", "charge_green_w", "-3"),
                     ("config", "gibt_es_nicht", "1"),
                     ("config", "zu", "viele", "worte")):
            rc, _, err = self.run_cmd(*argv)
            self.assertEqual(rc, 2, argv)
            self.assertTrue(err)

    def test_config_does_not_let_thresholds_cross(self):
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

    def test_reset_puts_it_back(self):
        self.set_theme(b.theme_name("base", "amber"))
        rc, _, _ = self.run_cmd("reset")
        self.assertEqual(rc, 0)
        self.assertEqual(b.Setting().get(), "base")

    def test_reset_is_repeatable(self):
        self.assertEqual(self.run_cmd("reset")[0], 0)
        self.assertEqual(b.Setting().get(), "base")

    def test_restore_clears_everything(self):
        self.make_theme("base")
        self.alle_themes()
        b.save_config(dict(b.DEFAULTS, discharging=True))
        self.set_theme(b.theme_name("base", "red"))
        rc, out, _ = self.run_cmd("restore")
        self.assertEqual(rc, 0)
        self.assertIn("3 colour theme(s)", out)
        self.assertIn("icon copies removed", out)
        self.assertEqual(b.Setting().get(), "base")
        self.assertFalse(os.path.exists(b.CONFIG))
        self.assertEqual(b.load_config(), b.DEFAULTS)

    def test_restore_with_nothing_there(self):
        rc, _, _ = self.run_cmd("restore")
        self.assertEqual(rc, 0)


class Logging(Base):
    """`battctl watch` - the measuring tool for the thresholds."""

    def test_quantile(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(b.quantil(values, 0.5), 6)
        self.assertEqual(b.quantil(values, 0.9), 9)
        self.assertEqual(b.quantil(values, 1.0), 10)
        self.assertEqual(b.quantil([7], 0.9), 7)
        self.assertIsNone(b.quantil([], 0.5))

    def test_writes_rows_and_a_summary(self):
        self.battery(status="Discharging", ampere=0.5, volt=3.9)
        path = os.path.join(self.tmp, "log.csv")
        rc, out, _ = self.run_cmd("watch", "0.2", "--interval", "0.05",
                                  "--csv", path)
        self.assertEqual(rc, 0)
        self.assertIn("time,state,watt,percent,screen", out)
        self.assertIn("Discharging:", out)
        self.assertIn("median", out)
        rows = open(path).read().splitlines()
        self.assertGreater(len(rows), 1)
        self.assertTrue(rows[1].startswith("2"))      # ISO-Datum

    def test_a_wobbling_run_says_so_itself(self):
        """A calibration run on a worn port should say so rather than hand
        over a median of noise."""
        self.battery(status="Charging", ampere=1.2, volt=4.3)

        echte_battery = self.battery
        counter = {"n": 0}

        def wechselnd(*a, **kw):
            counter["n"] += 1
            echte_battery(status="Charging" if counter["n"] % 2 else
                          "Discharging", ampere=1.2, volt=4.3)

        # The state changes between readings.
        import threading
        stop = threading.Event()

        def ruettler():
            while not stop.is_set():
                wechselnd()
                stop.wait(0.02)

        t = threading.Thread(target=ruettler)
        t.start()
        try:
            _rc, out, _ = self.run_cmd("watch", "0.4", "--interval", "0.05")
        finally:
            stop.set()
            t.join()
        self.assertIn("direction changed", out)
        self.assertIn("not a baseline", out)

    def test_an_unreadable_battery_writes_no_rows(self):
        rc, out, _ = self.run_cmd("watch", "0.1", "--interval", "0.05")
        self.assertEqual(rc, 0)
        self.assertNotIn("Discharging:", out)

    # -------------------------------------------------- Auswertung

    def log(self, rows):
        path = os.path.join(self.tmp, "log.csv")
        with open(path, "w") as fh:
            fh.write("time,state,watt,percent,screen\n")
            for i, (state, watt, licht) in enumerate(rows):
                fh.write("2026-09-15T12:%02d:00,%s,%.3f,80,%s\n"
                         % (i % 60, state, watt, licht))
        return path

    def test_reads_past_broken_rows(self):
        path = self.log([("Discharging", 1.0, 100)])
        with open(path, "a") as fh:
            fh.write("abgeschnitten\n2026,Discharging,keine-zahl,80,100\n")
        rows, error = b.read_log(path)
        self.assertIsNone(error)
        self.assertEqual(len(rows), 1)

    def test_a_missing_file_is_a_sentence_not_a_crash(self):
        rows, error = b.read_log(os.path.join(self.tmp, "not-there"))
        self.assertEqual([], rows)
        self.assertIn("not-there", error)

    def test_an_empty_log(self):
        path = self.log([])
        _zeilen, error = b.read_log(path)
        self.assertIn("no readings", error)

    def test_the_screen_column_in_both_spellings(self):
        """The panel's DPMS state and - where there is none - the
        Helligkeit als Zahl."""
        rows, _ = b.read_log(self.log(
            [("Discharging", 1.0, "On"), ("Discharging", 1.0, "Off"),
             ("Discharging", 1.0, 700), ("Discharging", 1.0, 0),
             ("Discharging", 1.0, "?")]))
        self.assertEqual([z["screen"] for z in rows],
                         [True, False, True, False, None])

    def test_screen_on_and_off_are_two_distributions(self):
        """Only one of them decides the thresholds: this icon is seen only
        by somebody looking at the screen."""
        rows, _ = b.read_log(self.log(
            [("Discharging", 0.2, 0)] * 10 + [("Discharging", 3.0, 800)] * 10))
        groups, _wechsel = b.summarise(rows)
        self.assertEqual(len(groups["Discharging"]), 20)
        self.assertEqual(len(groups["Discharging, screen off"]), 10)
        self.assertEqual(b.quantil(groups["Discharging, screen on"], 0.5), 3.0)

    def test_direction_changes_are_counted(self):
        rows, _ = b.read_log(self.log(
            [("Charging", 1.0, 100), ("Discharging", 1.0, 100),
             ("Discharging", 1.0, 100), ("Charging", 1.0, 100)]))
        self.assertEqual(b.summarise(rows)[1], 2)

    def test_the_suggestion_needs_enough_readings(self):
        self.assertIsNone(b.suggestion([1.0] * 29))
        self.assertIsNone(b.suggestion([]))

    def test_and_enough_spread(self):
        """All the same number means there is no "unusual" to find."""
        self.assertIsNone(b.suggestion([2.0] * 50))

    def test_the_suggestion_is_p90_and_p98(self):
        # Ninety ordinary readings, nine busier ones, one spike.
        values = [1.0] * 90 + [5.0] * 9 + [9.0]
        self.assertEqual(b.suggestion(values), (1.0, 5.0))

    def test_summarise_names_both_and_writes_nothing(self):
        path = self.log([("Discharging", 1.0, 700)] * 90
                        + [("Discharging", 5.0, 700)] * 9
                        + [("Discharging", 9.0, 700)])
        rc, out, _ = self.run_cmd("summarise", path)
        self.assertEqual(rc, 0)
        self.assertIn("Suggested: drain_amber_w 1.0", out)
        self.assertIn("drain_red_w 5.0", out)
        self.assertEqual(b.load_config()["drain_amber_w"],
                         b.DEFAULTS["drain_amber_w"])

    def test_only_with_apply_are_they_set(self):
        path = self.log([("Discharging", 1.0, 700)] * 90
                        + [("Discharging", 5.0, 700)] * 9
                        + [("Discharging", 9.0, 700)])
        rc, out, _ = self.run_cmd("summarise", path, "--apply")
        self.assertEqual(rc, 0)
        self.assertIn("Set.", out)
        cfg = b.load_config()
        self.assertEqual(cfg["drain_amber_w"], 1.0)
        self.assertEqual(cfg["drain_red_w"], 5.0)

    def test_too_few_readings_set_nothing(self):
        path = self.log([("Discharging", 1.0, 700)] * 5)
        rc, out, _ = self.run_cmd("summarise", path, "--apply")
        self.assertEqual(rc, 1)
        self.assertIn("Not enough", out)
        self.assertEqual(b.load_config()["drain_amber_w"],
                         b.DEFAULTS["drain_amber_w"])

    def test_summarise_without_a_path(self):
        for argv in (("summarise",), ("summarise", "--wat", "x")):
            rc, _, err = self.run_cmd(*argv)
            self.assertEqual(rc, 2)
            self.assertIn("Usage", err)

    def test_summarize_is_accepted_too(self):
        path = self.log([("Discharging", 1.0, 700)])
        self.assertEqual(self.run_cmd("summarize", path)[0], 1)

    def test_nonsense_arguments(self):
        rc, _, err = self.run_cmd("watch", "vielleicht")
        self.assertEqual(rc, 2)
        self.assertIn("Usage", err)


class TheLoop(Base):
    """The daemon's decisions, driven by a clock the test holds."""

    def setUp(self):
        super().setUp()
        self.make_theme("base")
        self.battery(ampere=1.2, volt=4.3)          # 5.16 W -> amber
        self.d = b.Daemon(current="base")

    def test_the_first_colour_comes_at_once(self):
        self.assertTrue(self.d.tick(now=1000))
        self.assertEqual(self.d.showing[0], "amber")
        self.assertEqual(b.Setting().get(), b.theme_name("base", "amber"))

    def test_the_same_colour_writes_nothing(self):
        self.d.tick(now=1000)
        self.assertFalse(self.d.tick(now=2000))

    def test_the_dwell_time_holds_the_colour(self):
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

    def test_the_median_smooths_an_outlier(self):
        for t in (1000, 1005, 1010):
            self.d.tick(now=t)
        self.battery(ampere=0.1, volt=4.3)          # ein Einbruch: 0.43 W
        self.d.tick(now=1015)
        self.assertEqual(self.d.showing[0], "amber")

    def test_old_readings_fall_out_of_the_window(self):
        self.d.tick(now=1000)
        self.d.tick(now=1000 + b.DEFAULTS["window_s"] + 1)
        self.assertEqual(len(self.d.samples), 1)

    def test_charging_and_discharging_are_not_mixed(self):
        """The median is taken over readings of the same direction only -
        3 W in and 3 W out are opposite verdicts."""
        self.d.cfg["discharging"] = True
        self.d.tick(now=1000)                       # charging at 5.16 W: amber
        self.battery(status="Discharging", ampere=1.6, volt=3.9)   # 6.24 W
        self.d.tick(now=1100)
        # As a charging power that would be green; as a drain it is red.
        self.assertEqual(self.d.showing[0], "red")

    def test_unplugging_takes_the_colour_away(self):
        self.d.tick(now=1000)
        self.battery(status="Discharging", ampere=0.5, volt=3.9)   # 1.95 W
        self.assertTrue(self.d.tick(now=1100))
        self.assertIsNone(self.d.showing[0])
        self.assertEqual(b.Setting().get(), "base")

    def test_full_takes_the_colour_away(self):
        self.d.tick(now=1000)
        self.battery(status="Full", ampere=0.0, volt=4.4)
        self.assertTrue(self.d.tick(now=1100))
        self.assertEqual(b.Setting().get(), "base")

    def test_an_unreadable_battery_leaves_the_colour_at_first(self):
        """A single failed read must not restyle every app on the phone."""
        self.d.tick(now=1000)
        os.unlink(os.path.join(self.sysfs, "current_now"))
        self.assertFalse(self.d.tick(now=1030))
        self.assertEqual(self.d.showing[0], "amber")

    def test_and_takes_it_away_if_it_stays_that_way(self):
        """But a colour nothing can justify any more is worse than none."""
        self.d.tick(now=1000)
        os.unlink(os.path.join(self.sysfs, "current_now"))
        self.assertTrue(self.d.tick(now=1000 + b.DEFAULTS["window_s"] + 1))
        self.assertIsNone(self.d.showing[0])
        self.assertEqual(b.Setting().get(), "base")

    def test_a_new_theme_of_the_users_is_adopted(self):
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

    def test_our_own_colour_is_not_a_new_theme(self):
        self.d.tick(now=1000)
        self.assertFalse(self.d.adopt(b.theme_name("base", "green")))
        self.assertEqual(self.d.base, "base")

    def test_adopts_a_colour_from_an_earlier_run(self):
        """After a crash the theme is still green. A fresh daemon has to
        start from what is on screen, or dwell and hysteresis both count from
        a colour nobody is looking at."""
        self.set_theme(b.theme_name("base", "green"))
        d = b.Daemon(current=b.theme_name("base", "green"))
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

    def test_without_a_usable_theme_nothing_happens(self):
        self.set_theme("does-not-exist")
        d = b.Daemon(current="does-not-exist")
        self.assertFalse(b.can_theme(d.base))
        self.assertFalse(d.tick(now=1000))

    def test_a_colour_without_a_theme_is_not_set(self):
        """apply() builds the themes if they are missing - and gives up
        quietly when the base theme cannot carry them."""
        self.set_theme("does-not-exist")
        d = b.Daemon(current="does-not-exist")
        self.assertFalse(d.apply(("green", None), now=1000))
        self.assertIsNone(d.showing[0])

    def test_a_theme_is_built_when_needed(self):
        d = b.Daemon(current="base")
        self.assertTrue(d.apply(("green", None), now=1000))
        self.assertEqual(b.Setting().get(), b.theme_name("base", "green"))

    def test_a_changed_config_takes_effect_without_a_restart(self):
        """The app writes the config file; a daemon that read it once would
        make its switch look broken until the next boot."""
        self.battery(status="Discharging", ampere=1.6, volt=3.9)   # 6.24 W
        self.assertFalse(self.d.tick(now=1000))     # discharging is off
        b.save_config(dict(b.DEFAULTS, discharging=True))
        self.assertTrue(self.d.tick(now=1100))
        self.assertEqual(self.d.showing[0], "red")

    def test_an_unchanged_config_is_not_reread(self):
        b.save_config(dict(b.DEFAULTS, charge_green_w=9.0))
        d = b.Daemon(current="base")
        self.assertFalse(d.reload())
        self.assertEqual(d.cfg["charge_green_w"], 9.0)

    def test_a_deleted_config_falls_back_to_defaults(self):
        b.save_config(dict(b.DEFAULTS, charge_green_w=9.0))
        d = b.Daemon(current="base")
        os.unlink(b.CONFIG)
        self.assertTrue(d.reload())
        self.assertEqual(d.cfg["charge_green_w"], 7.0)

    def test_the_filling_does_not_switch_the_shell_with_it(self):
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

    def test_the_filling_colours_even_without_a_shell(self):
        """On battery with an ordinary drain the shell says nothing - the
        filling still says the battery is nearly empty.

        With an icon that has two areas - either one of the three Adwaita
        draws that way itself, or one of our own copies. The single-shape
        case is the test below.
        """
        self.icon_with_two_areas("battery-level-10-symbolic")
        self.battery(status="Discharging", ampere=0.2, volt=3.9, percent=8)
        self.assertTrue(self.d.tick(now=1000))
        self.assertEqual(self.d.showing, (None, "red"))
        self.assertEqual(b.Setting().get(), b.theme_name("base", None, "red"))

    def test_an_icon_of_one_piece_gets_one_colour(self):
        """The plain discharge icon is a single path, so colouring shell and
        filling differently would mean one of them silently overwriting the
        other. The more urgent one speaks for the whole icon."""
        self.d.icon = "battery-level-90-symbolic"
        self.d.cfg["discharging"] = True
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=90)
        self.d.tick(now=1000)              # 6.24 W: Huelle red_at, Stand egal
        self.assertEqual(self.d.showing, ("red", "red"))

    def test_and_the_more_urgent_one_wins(self):
        """Half full and drawing hard: the level would say amber, the drain
        says red, and one shape can only say one of them."""
        # No icon with two areas in the search path: the discharge icon is
        # then one of a single piece.
        self.d.cfg["discharging"] = True
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=50)
        self.d.tick(now=1000)              # 6.24 W
        self.assertEqual(self.d.showing, ("red", "red"))

    def test_while_charging_there_are_two(self):
        self.d.icon = "battery-level-50-charging-symbolic"
        self.battery(ampere=1.2, volt=4.3, percent=50)   # 5.16 W: amber
        self.d.tick(now=1000)
        self.assertEqual(self.d.showing, ("amber", "amber"))
        self.battery(ampere=2.5, volt=4.3, percent=50)   # 10.75 W: green
        self.d.tick(now=1100)
        self.assertEqual(self.d.showing, ("green", "amber"))

    def test_on_a_contradiction_only_the_level_is_coloured(self):
        self.d.icon = "battery-full-symbolic"      # no bolt
        self.battery(status="Charging", ampere=0.2, volt=4.3, percent=85)
        self.assertFalse(self.d.tick(now=1000))
        self.assertEqual(self.d.showing, (None, None))
        self.assertEqual(b.Setting().get(), "base")

    def test_a_wobbling_direction_leaves_the_shell_plain(self):
        """A worn USB port flips between charging and discharging every few
        minutes. Following that would restyle every GTK3 app about once a
        minute for something the cable is doing."""
        self.d.cfg["discharging"] = True
        self.battery(status="Charging", ampere=1.2, volt=4.3, percent=80)
        self.d.tick(now=1000)
        self.assertEqual(self.d.showing[0], "amber")
        # The plug wobbles: still inside the same window, other direction.
        # 1050, not 1100: after a whole window length the old reading would
        # be out and the direction unambiguous again - the test would then
        # check the opposite.
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=80)
        self.assertTrue(self.d.tick(now=1050))
        self.assertIsNone(self.d.showing[0])

    def test_and_colours_again_once_it_has_settled(self):
        self.d.cfg["discharging"] = True
        self.battery(status="Charging", ampere=1.2, volt=4.3, percent=80)
        self.d.tick(now=1000)
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=80)
        self.d.tick(now=1050)
        self.assertIsNone(self.d.showing[0])
        # A whole window long, only the one direction
        self.d.tick(now=1050 + b.DEFAULTS["window_s"] + 1)
        self.assertEqual(self.d.showing[0], "red")

    def test_the_level_does_not_wobble_along(self):
        """The level is the same number whichever way the current is
        flowing, so it keeps its colour while the direction is unsettled."""
        self.icon_with_two_areas("battery-level-10-charging-symbolic")
        self.icon_with_two_areas("battery-level-10-symbolic")
        self.battery(status="Charging", ampere=1.2, volt=4.3, percent=9)
        self.d.tick(now=1000)
        self.battery(status="Discharging", ampere=1.2, volt=3.9, percent=9)
        self.d.tick(now=1050)
        self.assertEqual(self.d.showing[1], "red")

    def test_while_charging_the_bolt_takes_the_power_colour(self):
        """Asked for: on a charging icon only the bolt says how fast, and
        the frame stays in the colour of the bar."""
        # One file, both areas - the second helper would overwrite the
        # first and take the bolt away again.
        self.icon_with_bolt("battery-level-80-charging-symbolic")
        self.battery(ampere=1.2, volt=4.3, percent=80)      # 5.16 W: amber
        self.d.tick(now=1000)
        self.assertEqual(self.d.kind, "c")
        self.assertTrue(b.Setting().get().endswith("-amber-none-c"))
        rule = open(os.path.join(self.themes, b.Setting().get(),
                                 "gtk-3.0", "gtk.css")).read()
        self.assertNotIn("  color:", rule)
        self.assertIn("warning %s" % b.COLORS["amber"], rule)

    def test_without_a_bolt_of_its_own_the_frame_takes_it(self):
        """Where our icon theme is not in use there is nothing to colour
        but the frame - and one colour is better than none."""
        self.icon_with_two_areas("battery-level-80-charging-symbolic")
        self.battery(ampere=1.2, volt=4.3, percent=80)
        self.d.tick(now=1000)
        self.assertEqual(self.d.kind, "d")
        self.assertTrue(b.Setting().get().endswith("-amber-none-d"))

    def test_on_battery_the_frame_takes_it(self):
        self.d.cfg["discharging"] = True
        self.icon_with_two_areas("battery-level-80-symbolic")
        self.battery(status="Discharging", ampere=1.6, volt=3.9, percent=80)
        self.d.tick(now=1000)
        self.assertEqual(self.d.kind, "d")
        rule = open(os.path.join(self.themes, b.Setting().get(),
                                 "gtk-3.0", "gtk.css")).read()
        self.assertIn("  color: %s" % b.COLORS["red"], rule)

    def test_setting_can_fail(self):
        class Stur(b.Setting):
            def set(self, name):
                return False
        d = b.Daemon(setting=Stur(self.setting), current="base")
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
