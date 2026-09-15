# battery — the battery icon says what it knows

While charging, the FuriPhone shows a bolt and a percentage. Both look the
same whether one watt is going in or six — and that is exactly the number
worth seeing: a tired cable, a laptop port or a charger that has quietly
renegotiated all look like "charging" and cost hours.

The icon has two parts, and from now on they say two different things:

| | what it says | |
|---|---|---|
| **the bolt**, while charging | how fast the battery is filling | green · amber · red |
| **the frame**, on battery | how much is being drawn | plain · amber · red |
| **the filling**, always | how full it is | plain · amber · red |

So: **green** when a lot is going in, **amber** in between, **red** when
hardly anything is moving — and the filling inside takes colour independently
of that when the charge level runs short.

While charging the power colour goes on the **bolt** alone, because there is
a bolt to carry it and the frame is then free to stay out of the way. On
battery there is no bolt, so the frame takes it.

![The states](doc/states.png)

(Drawn with GTK's own renderer from the real icons, not painted by hand:
`python3 doc/make-states.py`. The thresholds in the chart are the
defaults — measured ones may differ.)

The colour of the frame on battery is switched off until somebody switches it
on; the filling always takes colour, because a nearly empty battery should
say so whether it is charging, discharging or full.

A wobbling connection — a broken socket, a tired plug — makes the phone jump
between charging and discharging. The frame does **not** follow that: it
stays plain as long as the readings of one minute do not agree about the
direction. Otherwise the colour would be an indicator of the cable.

For this to work at all, `battctl` brings an **icon theme** of its own:
Adwaita draws the discharge battery as ONE path with the level inside it,
and frame and bolt of the charging battery as one path as well - no CSS
reaches either alone. The theme inherits the user's own theme and replaces
eighteen files with versions whose filling, and whose bolt, are paths of
their own; it lives under `~/.local/share/icons` and goes away again with
`battctl restore`.

Its name carries a fingerprint too (`furios-battery-f8ba`), for the same
reason the GTK theme does: GTK caches an icon theme by name, so a file added
to a theme already in use stays invisible. Measured, while building this:
the bolt icons arrived and the shell went on drawing Adwaita's.

A theme, and not a few files in `~/.local/share/icons/Adwaita`: that would be
the shorter way and it has a trap. GTK remembers where it found an icon; when
that file disappears, the bar draws the placeholder icon and does not recover
— not even when the file is written straight back. Only a change of the theme
setting makes GTK look again, which is why that setting is both the way in
and the way out here. Where a version is missing, the display falls back to
one colour for the whole icon — the more urgent of the two.

And when the kernel and UPower contradict each other about the direction, the
frame stays plain: phosh then draws an icon the colour does not fit. Details
in FINDINGS.md.

```
git clone https://github.com/misc-de/furios_misc
cd furios_misc/battery
./install.sh                 # NEVER with sudo - it needs no root at all
systemctl --user enable --now furios-battery-color.service
```

Or in the app *misc-de*, under **Battery**.

## How the colour reaches the icon

phosh is GTK3, and its battery icon is the CSS node `phosh-battery-info`. One
line of CSS colours it:

```css
phosh-battery-info image {
  -gtk-icon-palette: success #ff7800, error #ff7800,   /* filling: < 60 %  */
                     warning #e01b24;                  /* bolt: 1 W in     */
}
```

The icon has up to three areas, and GTK can address them separately:
`color` reaches everything without a class, `success` and `error` the
filling (the low-level icons draw it with the second one), and `warning` the
bolt - the last one only in our own copies, because Adwaita draws frame and
bolt together.

Only the halves that have something to say appear. A palette that named all
three would paint the filling in the colour of the bolt whenever the level
is fine - an 84 % battery went orange that way, on the phone, once.

Where one of the two statements is absent, the line is absent: a rule without
`color` leaves the frame in the colour of the bar, one without the palette
leaves the filling in it. Writing a "white" would mean guessing at a
foreground we cannot read.

The obvious place for all this is `~/.config/gtk-3.0/gtk.css` — and it is a
dead end: GTK3 reads that file **once at program start** and never again. A
colour that changes would therefore need the shell restarted at every change,
and that is the one thing not to do on this phone.

What GTK3 does re-read at runtime is the **theme**. A
`gsettings set org.gnome.desktop.interface gtk-theme …` restyles every
running GTK 3 application within a second, phosh included. So this project
writes themes that are nothing more than the user's theme plus that one rule,
and switches between them:

```
~/.themes/adw-gtk3-batt7e17-red-amber/gtk-3.0/gtk.css
    @import url("file:///usr/share/themes/adw-gtk3/gtk-3.0/gtk.css");
    phosh-battery-info image { color: …; -gtk-icon-palette: …; }
```

The name carries both halves, because both stand in the same file. The
combinations are written only when they are needed — twelve directories in
`~/.themes` would be twelve entries in every theme chooser on the phone.

The four characters in the name are the fingerprint of the rule. They are
there because GTK3 caches a named theme **for the lifetime of the process**,
by name and without a second look at the file: change the rule and keep the
name, and phosh keeps showing the version from back then until the next
restart.

**What that costs** — this belongs before the decision, not after it: every
change briefly restyles all GTK 3 applications, and the theme setting shows
one of our names while it lasts. It happens at a colour change, not
continuously: a handful of times per charge. Anybody who changes their theme
themselves is not overruled — the service notices, builds on the new one and
carries the colour over.

## Thresholds

| | plain | green | amber | red |
|---|---|---|---|---|
| bolt, charging | — | from 7 W | from 3 W | below that |
| frame, on battery | below 2 W | — | from 2 W | from 4 W |
| filling | above 60 % | — | below 60 % | below 15 % |

On battery, **plain is the normal case**: a phone doing what a phone does
says nothing, and only an unusual drain speaks up. There is no green there —
a colour that shines all day is not a message any more.

The values are **provisional**. They belong measured, not guessed — that is
what `battctl watch` is for:

```
battctl watch 3600 --csv ~/drain.csv          # write along for an hour
```

…and `battctl summarise`, which evaluates such a log:

```
battctl summarise ~/drain.csv            # what is in it and what it suggests
battctl summarise ~/drain.csv --apply    # and sets it
```

It splits by state AND by screen, and the thresholds come **only from the
half with the screen on**: this icon is seen only by somebody looking, so
"normal" is what the phone draws in use. What it suggests is **amber at p90,
red at p98** — then the unusual tenth speaks up and the rest stays plain.
Below 30 readings with the screen on, or when p90 and p98 land on the same
number, it sets nothing and says why.

Important here: for the battery case what counts is the drain with the
**screen on**. The 0.2 W of a phone on a table is no sensible baseline. The
log therefore carries the state of the panel along in a column.

The phone negotiates 12.7 W over USB-PD, but at most 5.9 W has been measured
so far — so the charging thresholds are not confirmed either.

```
battctl config charge-green-w 6
battctl config drain-amber-w 2.5
battctl config discharging on
battctl config level-amber-pct 50
battctl config level off        # do not colour the filling at all
battctl config                  # everything there is
```

So that the colour does not flicker on the noise — `current_now` jumps by a
quarter of an amp between two readings — it is not the last value that
decides but the **median** of a minute; a threshold has to be crossed by a
tenth before the colour follows, and every colour stays for at least 45
seconds.

## What it touches

Nothing it would need root for. It reads four files under
`/sys/class/power_supply/battery`, writes `~/.themes` and
`~/.local/share/icons`, and sets two gsettings keys. `battctl restore` takes
all of that back, `./uninstall.sh` the program as well.

The clock is **UPower**: it polls the battery for the whole phone anyway, so
its signal is subscribed to rather than polling ourselves. A slow timer
(120 s) runs underneath as a net.

## Tests

```
tests/run-tests.sh      # no display, no battery, no root - NEVER with sudo
tests/coverage.sh
```

159 tests, 88.0 % of the lines. What is missing is the D-Bus wiring of the
daemon — that is proven on the device, not simulated (FINDINGS.md).
