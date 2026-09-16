# What was measured while building this

All of it measured on the FuriPhone FLX1, FuriOS with phosh 0.55,
GTK 3.24.52, kernel 4.19.325.

## 1 · The charging power is in the battery itself

```
/sys/class/power_supply/battery/current_now   in µA
/sys/class/power_supply/battery/voltage_now   in µV
/sys/class/power_supply/battery/status        Charging | Discharging | Full | Not charging
```

The product is the power **into the battery**. On 15.9.2026 at 14:19 that was
1.07-1.36 A at 4.32 V, so **4.6-5.9 W**; two minutes later only 0.23-0.46 A,
so **1.0-1.9 W**, and `time_to_full_now` jumped from 49 to 200 minutes.

The drop is **explained, and outside the software**: the USB socket of this
device is broken, the connection wobbles (told by the user, 15.9.). Everything
thermal had already been ruled out (battery 36.6 °C and falling, `sw_jeita` =
0, no thermal zone above 45 °C), and so had the CV phase (charge level 76 %,
too early for it).

It is measurable in the **direction**: in 26 minutes the state changed nine
times between `Charging` and `Discharging`. Two consequences:

- Calibrating the CHARGING thresholds is pointless on this device for now.
  `battctl watch` counts the direction changes and says so by itself
  ("direction changed N times ... not a baseline"). The discharge side stays
  usable.
- The service must not follow a wobbling direction. Every colour change
  restyles all GTK 3 applications, and measured that would have been about
  once a minute — for something the cable is doing and not the battery. The
  frame therefore stays plain as long as the readings of a whole window do
  not agree about the direction. The charge level keeps its colour: the
  percentage is the same number whichever way the current is flowing.

The instantaneous values swing by **±0.3 A** from second to second. The
driver's `current_avg` smooths but lags badly (0.84 → 0.45 A in one minute).
Hence a median of our own, over one minute.

## 2 · Nothing can be measured on the wall side

- Kernel 4.19 does not have the `usb_power_delivery` class yet — no
  negotiated contract, no VBUS current.
- `/sys/devices/platform/charger/{input_current,chg1_current,chg2_current}`
  all deliver `4294967295` (0xFFFFFFFF, "not set") and are worthless.
- Usable are only `ADC_Charger_Voltage` = **4587 mV** (so a 5 V contract) and
  `pdc_max_watt` = **12684000** µW = **12.68 W** as the negotiated maximum.
  The battery took an eighth of that at times.
- `/sys/class/typec/port0/power_operation_mode` says `usb_power_delivery`.

## 3 · A driver bug you trip over at battery health

```
charge_full         4370000 µAh
charge_full_design   437000 µAh     <- a factor of 10 too small
```

That is why upower claims `energy-full-design: 1.89 Wh` and
`capacity: 100 %`. Upower's health figure is **meaningless** on this phone.
The real numbers: 4370 mAh, 205 charge cycles.

## 4 · The dead end: ~/.config/gtk-3.0/gtk.css

GTK3 reads the user file **once at the start** of the program. Two
measurements:

- The file did not exist here at all when phosh started — so phosh has no
  user provider whatsoever. Created it, waited three seconds, screenshot:
  unchanged.
- Even with the file, every change would only take effect at the next start.
  For a colour that changes hourly that would mean: restart the shell, and
  that is the one thing not to do on this phone
  (`OnFailure=gnome-session-shutdown`).

## 5 · What works live: the theme name

`gsettings set org.gnome.desktop.interface gtk-theme <name>` takes effect at
once. Proven on the device with screenshots (`grim`, which works over
zwlr_screencopy on phoc — package `grim`, not preinstalled):

1. Starting point: icon white.
2. Theme `furios-batt-test` (adw-gtk3 plus `color: #ff00ff` on
   `phosh-battery-info, … image, … label`) → icon **and** percentage
   magenta, **without** touching phosh.
3. Theme `furios-batt-test2` with
   `phosh-battery-info image { color: #2ec27e }` → icon green, percentage
   stays white. The switch from one theme of ours to the next works the same
   way — so it is repeatable, not merely "something different once".
4. Back to `adw-gtk3` → white again.

The CSS node is called `phosh-battery-info`. Found not in the inspector (that
would need the shell restarted) but in the resources:

```
gresource list /usr/libexec/phosh | grep css
gresource extract /usr/libexec/phosh /mobi/phosh/stylesheet/common.css
strings /usr/libexec/phosh | grep phosh-battery
```

## 5a · The icon has two paths, and one stayed white

Seen on the device after the first version was running: frame and bolt red,
the **filling white**. The Adwaita SVG explains it:

```
<path class="success" d="m 5 7 v 6 h 3 …" fill="#33d17a"/>   <- the level
<path d="m 7 0 c -1 0 …" fill="#2e3434"/>                     <- frame+bolt
```

`color` only colours the second. The first comes from GTK3's symbolic palette
and is set with `-gtk-icon-palette: success …, warning …, error …`. Proven
headless (`Gtk.IconInfo.load_symbolic`): with success=red, 112 of 112 opaque
pixels are red; with success=white exactly 24 stay white — that is the
filling. `Gtk.CssProvider` accepts the property without a parsing error.

All three palette names get the same colour: below 20 % the filling is
`warning` or `error` rather than `success`. The colour should come from the
charge level and not from which file phosh grabbed.

**And out of that came the actual division** (decided by the user, 15.9. in
the evening): the two paths say two different things — the frame the power,
the filling the charge level (plain above 60 %, amber below, red below 15 %).
Both stand in the same rule, so the theme name carries both halves
(`adw-gtk3-batt7e17-red-amber`), and the combinations are written only when
they are needed: twelve directories in ~/.themes would be twelve entries in
every theme chooser. Proven on the device by moving the threshold to 90 % for
a minute: red frame at 1.1 W, amber filling at 85 % — one icon, two
statements.

## 5b · GTK3 remembers a theme by NAME, not by file

`gtk_css_provider_get_named()` keeps loaded themes in a static table, for the
lifetime of the process, without looking at the file again. Changing the rule
and keeping the name therefore means: the file on disk is right, phosh shows
the old version until the next restart, and nothing says why. The theme name
therefore carries four characters of a SHA-1 of the rule
(`adw-gtk3-batt7e17-…`). Older generations are removed while the new ones are
written, so a directory does not accumulate per update.

## 5c · The battery icons are THREE families, built differently

Noticed because the icon was suddenly completely red. Adwaita does not draw
one icon with variants, it draws three sorts:

| File | Paths | `color` colours | palette colours |
|---|---|---|---|
| `battery-level-NN-charging-symbolic` | 2 | frame + bolt | the filling |
| `battery-level-NN-plugged-in-symbolic` | 2 | the frame | the filling |
| `battery-level-NN-symbolic` | **1** | **everything** | **nothing** |

Of the twelve discharge icons only three (0, 10, 20 %) have a second path —
there Adwaita colours the remainder as a warning itself. For the other nine
there are simply no two halves, and `color` paints the whole icon.

Consequence at first: the division "frame = power, filling = level" only
holds where the icon allows it. On an icon of one piece the **more urgent**
of the two colours gets the whole icon (red > amber > green > nothing).

**SOLVED by laying the missing area underneath the icon** (the user's wish,
15.9. in the evening: on battery colour only the frame and show the charge
level separately). The filling is a subpath of its own in these files, but in
relative coordinates — extracting it would mean parsing the path. Instead an
identical rectangle with `class="success"` goes ON TOP; the geometry is the
icon's own (x 5, width 6, bottom at 13, one unit per 12.5 %) and was checked
against the originals at 100, 90, 50 and 30 % — the rectangle covers the
original area exactly, no edge shows through.

The eight versions live in an icon theme of their own,
`~/.local/share/icons/furios-battery`, which inherits the user's theme;
`/usr/share` stays untouched. Without a palette set they look like the
originals, so nothing changes for other programs. The merging above remains
as the fallback for icons we have no version of.

**The first attempt was NOT a theme of its own** — the files lay under
`~/.local/share/icons/Adwaita` and shadowed the system files. That worked at
the first try and has a trap that went off on the device: GTK remembers WHERE
it found an icon. When that file disappears, the bar paints the placeholder
icon — and it does not recover, not even when the file is written straight
back (measured: file back, icon still broken). Only a change of the theme
setting makes GTK look again. Hence a theme now:
`gsettings set … icon-theme` is the way in, the same switch back is the way
out, and `battctl restore` ALWAYS sets the setting back first and deletes
only afterwards.

What set that off was a fault in our own tests: `cmd_restore` called
`remove_split_icons()` without an argument while the test environment
redirected only SYSFS, CONFIG and THEMES — not the icon directory. A test run
thereby deleted the icons of the running phone. The test base now redirects
EVERY path that points into the real home (`ICON_BASE`, `ICON_SOURCE`,
`ICON_DIRS` and the second gsettings file), and the comment there says why
that is not fussiness.

**And the name phosh draws is not the one from UPower**: phosh builds
`battery-level-%d-symbolic` itself (read out of the binary), UPower reports
`battery-full-symbolic` — two different files, from two directories, built
differently. Asking the wrong one gives the wrong answer to "does this icon
have two areas".

## 5e · The bolt, on its own

Asked for on 15.9. in the evening: while charging, colour only the bolt and
leave the frame alone. Adwaita does not allow that either - frame and bolt
are two subpaths of ONE path, and `color` reaches both or neither.

The bolt is the second subpath. The first ends with `z`, so the current
point is back at the path's own start (7,0) and the bolt's relative
"m 6 8" is the absolute (13,8). Checked against all ten charging icons:
identical structure in every one - same start, same closing `z`, same
delta. Where that does not hold, no bolt is generated: a misplaced copy
would be a magenta smear next to the battery, and no colour is better than
that.

The copy carries `class="warning"`, which is free in the charging icons -
they use only `success`, for the filling. So the three areas map onto the
three levers GTK has:

| area | comes from |
|---|---|
| frame | `color` |
| filling | palette `success`, and `error` for the low-level icons |
| bolt | palette `warning` (our copies only) |

Two things that went wrong in the first attempt, both visible in one
screenshot of an 84 % battery: the **filling** went orange instead of the
bolt, because the palette named all three entries and the half that had
nothing to say repeated the one that did; and the **bolt stayed white**,
because the icon theme had not changed its name - GTK caches an icon theme
the way it caches a GTK theme, so the new files were invisible until the
name carried a fingerprint of its own (`furios-battery-f8ba`).

Where our copies are not in use, the power colour goes back on the frame:
one colour is better than none, and the daemon can tell the difference by
reading the file it knows phosh will draw.

## 5d · The kernel and UPower contradict each other

Measured on 15.9. while the charger was playing up:

```
/sys/.../status   Charging      current_now x voltage_now = 1.8 W
upower            discharging   energy-rate 0 W   icon battery-full-symbolic
```

phosh follows UPower, so it drew the icon WITHOUT a bolt — and we painted a
charging-power colour onto it. From the user's point of view: a completely
red battery icon at 86 % with no visible reason.

The rule from that: **while the two contradict each other, the frame gets no
colour at all.** A colour that answers a question the picture does not ask is
worse than none. The charge level keeps its colour — both sources agree about
that.

## 6 · The trap that would have recoloured the whole phone

GTK3 takes `gtk-dark.css` when the file exists and the session prefers dark.
A generated theme that creates a `gtk-dark.css` although the base theme has
none thereby puts the **light** sheet under the interface in dark mode — the
colour would be right and the phone would look different. `write_theme`
therefore writes the dark sheet only when the base theme has one, and deletes
it again when it disappears. Test:
`test_no_dark_sheet_is_invented`.

## 7 · Two traps in our own tooling

- **`python3 -m trace` + `unittest.main()` = "Ran 0 tests"**, silently, with
  exit code 0 and a coverage report of 16 %. `unittest.main()` looks for
  tests in `sys.modules["__main__"]`, and under the tracer that is the
  tracer. The suite is therefore built by hand out of `globals()` (the same
  solution as in furios_app).
- **The coverage report unmasked a test that passed for the wrong reason**:
  `test_the_dwell_time_holds_the_colour` jumped from 5.2 W to 8.6 W and
  expected the dwell time to hold the change back. The median of the two
  readings was 6.9 W, the hysteresis demanded 7.7 W — the colour stayed
  because it was the same one anyway, and the dwell time was never reached.
  The line `return False` stayed unreached and gave it away.

## 7a · The thresholds are not measured yet

The defaults (charging 7/3 W, on battery 2/4 W) are guessed and marked as
provisional. `battctl watch` writes the series along and reports median, p90,
p98 and maximum at the end, split by charging and discharging;
`battctl summarise` evaluates such a log and suggests thresholds.

For the battery case what counts is explicitly the drain with the **screen
on**: the icon is seen only by somebody looking, so "normal" is what the
phone draws in use and not the idle load on a table.

What is NOT good for that, both measured here: `loginctl … IdleHint` stood at
`no` with the screen dark, and `/sys/class/leds/lcd-backlight/brightness`
kept its last value (629 of 2047). Both can say "off" and neither can say
"on". The panel's DPMS state can:
`/sys/class/drm/card0-DSI-1/dpms` is a state and not a value somebody left
behind, and that is what the log records.

## 8 · What is NOT checked here

The D-Bus wiring of the daemon (the UPower subscription, signal handling, the
main loop) has no tests — a subscription is hard to simulate, and a simulated
one would be no proof. It is proven on the device: start the service, pull
the cable, plug it in, journal and screenshot.

Plus the warning from a sibling project, which is built in here: a
subscription whose connection is collected expires **silently** — no error,
no journal entry, a healthy-looking service that never measures again. The
proxy is therefore held, and the 120 s timer runs underneath as a net.

## 9 · The time left: where a number can go in phosh's bar

Measured on 16.9.2026 on this 720 px screen, with `grim` and a script that
reads the ink positions out of the screenshot. Everything below is in screen
pixels, and every number was stepped and re-read rather than derived.

**There is no room to the right of the battery icon.** Switching the
percentage off with `org.gnome.desktop.interface show-battery-percentage`
frees its place and phosh moves the icons straight into it:

| | location | battery | percentage | padding |
|---|---|---|---|---|
| percentage on | 577–595 | 613–631 | 644–686 | 33 px |
| percentage off | 630–647 | 666–683 | — | 36 px |

So the place only exists while phosh is still laying the percentage out.
That is why the key stays **on** and the text is emptied by the theme
instead — and why this is the one stylesheet rule in this project that is
not a colour.

**The rule needs all three declarations.** `color: transparent` alone leaves
the slot exactly as wide as the percentage's own text, which means 9 %, 48 %
and 100 % reserve three different widths and the icons walk about under the
clock as the battery empties. `font-size: 1px` takes that decision away from
the text, and `min-width` then sets it. The value is not derivable: at
`min-width: 28px` the icons sat at 579/615 and at 30px at 576/612, so 29
reproduced the percentage's own layout — and once the font grew to 16 px the
right value was 41, because the slot has to hold **our** text, not phosh's.

**The font is phosh's own**, taken from its stylesheet rather than guessed:
`gresource extract /usr/libexec/phosh /mobi/phosh/stylesheet/common.css`
gives `font-size: 13px; font-weight: 800; font-feature-settings: "tnum"`
for `.indicators`. `tnum` is the one that matters — with proportional digits
a clock changes width at every digit and shifts under itself once a minute.
The size is ours at 16 px (phosh's clock size): 13 px was too small to read.

**The lock screen cannot be drawn on.** phoc speaks `zwlr_layer_shell_v1`
and has no session-lock protocol, so phosh's lock screen is an ordinary
layer surface on the same OVERLAY layer we use, and within a layer the
newest is on top — measured directly with two strips side by side, the one
started second covers the first. The lock screen is created when the phone
is locked, i.e. after us, so it covers us.

Two ways out were measured and both failed. Rebuilding the strip on the lock
signal leaves **no strip at all**: locking turns the panel off in the same
breath, and a layer surface created against an output that is off is never
configured. `PowerSaveMode` from `org.gnome.Mutter.DisplayConfig` looked like
the signal for "the screen came back on" and is not — it was emitted on one
lock cycle and not on the next. What is left is to lift the blanking for as
long as the phone is locked, so the lock screen looks exactly as it did
before the option existed.

`org.gnome.ScreenSaver.ActiveChanged` is dependable, and `SetActive` both
locks **and unlocks** this session without a PIN — which is how the lock
cycles above were driven. `loginctl lock-session` cannot: it answers
"Session does not support lock screen".

## 10 · A fork per reading is two thirds of the cost

The percentage key was read through `gsettings` on every tick, the way
`battctl config` reads it. Measured with `/proc/<pid>/stat`: the daemon used
0.217 % of a core, and **0.29 s of every 60 was child processes** — two
thirds of everything it spent, for one `gsettings get` per reading.

The theme key had been given a `Gio.Settings` of its own long ago for
exactly this reason. The new key went in through the front door and undid
it. Both are read in-process now.

The lesson is not about this key: anything called once per reading in a
daemon that never suspends is measured before it is believed, and the
cheapest way to measure it is the `cutime`/`cstime` fields of
`/proc/<pid>/stat`, which separate a process's own cost from what it forks.

## 11 · A switch is only as fast as the daemon's slowest clock

Switching "time left" on took **up to two minutes** to reach the bar. The
config was written at once and read only in `tick()`, and `tick()` has two
clocks: UPower's `PropertiesChanged` and a 120 s fallback timer. Nothing
about the switch itself was slow — nobody was listening for it.

A `GFileMonitor` on the config's **directory** (renamed into place, so the
inode changes with every write) now wakes the same tick. Measured on the
device on 16.9.2026, from the write to the daemon's own log line:

```
runtime off   0.145 s
runtime on    0.134 s
```

The trap is in the same directory: `state.json` is written by the daemon on
**every** tick, so an unguarded monitor is a loop — write, wake, tick, write.
`is_config_write` is the guard, and it has two halves, the name and a changed
stamp; the loop it prevents is what its tests are about. The daemon still
costs 1 CPU tick in 20 s afterwards, so the monitor is free.

## 12 · UPower already knows, and it still needs the window

The time was ours to work out: missing charge over current. UPower keeps a
history of this battery and publishes `TimeToFull` and `TimeToEmpty` on the
device object the daemon is **already subscribed to** for its clock - so both
numbers arrive cached with the wake-up and cost nothing to read.

The gap between the two, measured on 16.9.2026 while the socket was dropping
out:

```
UPower      3:03
ours       51:36     (charge over current_now, same instant)
```

But UPower's estimate is not calm either. Six reads, two seconds apart, on a
steady discharge:

```
11:08  08:47  10:11  08:24  10:34  09:33
```

So it goes through the same five-minute median as everything else. What that
buys, measured with a shadow daemon on the phone while the cable flickered:

```
          UPower raw   bar
20:25:22     01:20     01:20
20:25:32       -       01:20     UPower had no answer; the window carried it
20:25:42     01:35     01:27     the median of the two
20:25:52       -       01:27
```

Ours stays as the fallback, for the minutes after a start when UPower answers
0 and for a phone whose UPower is not running.

**And the ceiling came down from 99 h to 24.** This battery holds 4.37 Ah:
nine hours from the weakest port that is still a charger, about eleven to
empty on a phone that never suspends. Anything past a day is not a time, it
is a cable out of a broken socket - measured at 0.065 A and "33 hours". The
bar shows the percentage instead, which is the one thing still true.

## 13 · What is still not checked

Beside the D-Bus wiring (§8): the strip itself. Whether a layer surface comes
up, where its ink lands and whether it takes touch are all questions for a
compositor, and the answers here came from `grim` and `WAYLAND_DEBUG`, not
from a test. The one decision that could be lifted out of it is, and has
seven: `strip_action` says what the strip should do this tick, and the three
cases worth getting right — the percentage switched off by hand, not
claiming it back on the next tick, and a switch off and on again clearing
that — are pinned there.

The liveness check next to it (`strip.alive`, so a compositor restart does
not leave the daemon holding a dead window) is not: it is one line in the
loop, and simulating a compositor going away would prove nothing about this
one.
