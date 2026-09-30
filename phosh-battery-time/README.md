# phosh-battery-time — the time left and the battery's colour

A plugin for phosh's top bar. It does two things for
[`battctl`](../battery/): it shows the time `battctl` writes for it — how
long the battery lasts, or how long until it is full — in the shell's own
indicator box, immediately left of the battery icon; and it puts the colour
`battctl` decides on that battery icon.

    04:38 🔋 76%

It is one C file. It reads two small files in `$XDG_RUNTIME_DIR`, believes
nothing about them, and does nothing else: every failure is "show nothing",
because this runs **inside phosh's process** and a shell that dies over an
odd battery reading would be a far worse bargain than a missing number.

## Why a plugin and not a window of our own

That is what `battctl` did first: a layer-shell strip over the top bar, in
the place the percentage is emptied out of.

It works, and it is invisible exactly when you want it. phoc has no
session-lock protocol, so phosh's lock screen is an ordinary layer surface on
the same `OVERLAY` layer — and within a layer the newest is on top. The lock
screen is created when the phone is locked, which is after us. Measured with
two strips side by side: the one started second covers the first.

A plugin is a widget **inside** phosh's indicator box, so it is drawn wherever
that box is, lock screen included. And nothing has to be taken away from the
percentage to make room, so the theme machinery the strip needs — a
stylesheet that empties `phosh-battery-info label` and holds its width — is
not needed at all.

## Where it stands, and why that took a priority

phosh's `PhoshStatusIconsBox` keeps its children in **descending priority**
and puts anything that is not a `PhoshStatusIcon` — a plain label, which is
what this was at first — at the very start of the box. So the time sat at the
left-hand end of the right-hand group, a location pin away from the battery
it talks about.

So this is a status icon now, and it derives from phosh's own
`PhoshStatusIcon`: one symbol, `phosh_status_icon_get_type`, left undefined
in the module and filled in by the shell that loads it — the way phosh's own
status-icon plugins do it. The type is registered at load time against the
sizes `g_type_query` reports, because the only phosh header on the system is
the one with the extension point names in it.

That alone is not enough. Every icon in the bar has priority 10, and the box
inserts a new child **in front of** the ones it ties with — so 10 lands left
of the location pin and 9 lands right of the percentage. Neither is beside
the battery. What works is to tie with the battery and nobody else: the
plugin finds `PhoshBatteryInfo` in the box, turns its priority down to 9,
takes 9 itself, and the tie puts it immediately in front.

It is one small write into a widget of the shell's, and it is given back when
this widget goes. It costs the battery nothing: the box drops what it cannot
fit from the right, and the battery already stood last.

## The size

The size of the percentage beside it, because it is a reading about the same
battery: `phosh-top-panel .indicators` — 13px, weight 800, tabular figures —
which the label inherits by standing in that box. Nothing here sets a font at
all.

It asked for the clock's 16px until 17.9.2026, with a stylesheet of its own on
that one widget. Next to the battery it belongs to, that read as a second
clock rather than as part of the reading.

## Install

    ./install.sh

Without `sudo`: it builds here and asks for root only for the two lines that
write into phosh's plugin directory. That directory is where root is needed —
phosh takes it from a compile-time constant (`PHOSH_PLUGINS_DIR`), so there is
no directory in the home the shell would look in. Checked against phosh 0.55.

It needs `build-essential`, `phosh-dev` and `libgtk-3-dev` to build, and
nothing at all to run.

**phosh reads its plugin directory once, when it starts.** A plugin put there
afterwards is found by nobody until the next start — the shell says so once,
`Custom status-icon 'furios-battery-time' not found`, and then goes quiet. So
after installing: **reboot.**

There is no lighter way. `mobi.phosh.Shell.service` refuses a manual start
and a manual stop (`Operation refused, unit … may be requested by dependency
only`), and taking the shell down by hand takes the session with it —
`OnFailure=gnome-session-shutdown.target`, `replace-irreversibly`.

`battctl status` says which way the time is being shown, and what is missing
if it is the other one.

## The colour

`battctl` writes `$XDG_RUNTIME_DIR/furios-battery-color`, a line per half:

    frame #e5a50a
    fill #e01b24

The widget turns that into one rule —
`image { color: …; -gtk-icon-palette: success …, warning …, error …; }` —
in a `GtkCssProvider` of its own, and adds that provider to the style
context of the battery icon's image, and to nothing else. A provider on one
widget's context reaches that widget alone: not the icons beside it, not the
rest of the shell, not any other program. It is taken off again when the
widget goes.

**While charging, only the bolt.** Adwaita draws the outline and the bolt
as one path, so `color` cannot tell them apart. On a `-charging` icon the
widget therefore leaves `color` out of the rule and draws the image itself:
GTK renders it into a surface of ours, the ink's bounding box says where the
16-unit icon landed, and inside a region around the bolt (read from the
SVGs: the frame stops at y 6 and x 10, the bolt starts at y 8 and x 9) the
icon's own coverage masks the `frame` colour. Anything that does not have
the measured shape is drawn uncoloured.

The file is not CSS. Two known words, each with a `#rrggbb`; anything else
in it means no colour at all, so nothing written there can reach further
than those two declarations.

Why here and not in a theme: until 24.9.2026 `battctl` coloured the icon by
switching `gtk-theme` to generated themes of its own. phosh applies the
accent colour only to the themes it knows by name, so the quick settings
went blue, and Flatpak apps that did not know the name lost their dark mode.
In here, no setting is read or written at all.

## Switching it on

Nothing here does. `battctl` adds `furios-battery-time` to the shell's
`status-icons` list while any of its options is on — a colour or a time —
takes it out again when none is, and writes the two files in between. The
list is read, changed and written back, so another plugin in it is left where
it is.

## How the two halves meet

One file, `$XDG_RUNTIME_DIR/furios-battery-time`:

- the daemon writes `04:38` into it — beside the target and renamed, so the
  widget never reads half a line;
- the widget watches the **directory**, not the file, because the renaming
  changes the inode under a file monitor;
- no file, an empty one, one longer than 16 bytes or one that is not UTF-8:
  the widget hides itself. A label is not a place to trust a file.

The runtime directory rather than a place of our own: it belongs to this
user, it is a tmpfs, and it is emptied when the session ends — so a time from
yesterday cannot be sitting there when the shell starts.

## Tests

    ./tests/run-tests.sh        # NEVER with sudo

It builds the plugin and then loads it the way `src/plugin-loader.c` does:
register the extension point, scan the directory, ask for the extension under
the name the settings hold, build the widget — and drive it through the file
it reads, including the files it must refuse. Everything that can go wrong
there goes wrong silently in the shell, which says one line and carries on.

It also builds the shell's shape around the widget: the plugin looks for
`PhoshStatusIconsBox` and `PhoshBatteryInfo` **by name**, since neither type
is in a header we have, so the test registers those two names itself and
checks what the plugin does with them — the battery's priority comes down to
meet it, no other icon is touched, the colour lands on the battery's image
and on no other widget (not even our own label), a file that is not a colour
leaves the battery plain, and the battery has its priority and its own
colour back when the widget goes.

Needs a display to build a GTK widget on, and phosh's library to derive the
type from; without either, or without phosh's headers, it says so and skips.

## Uninstall

    ./uninstall.sh

Takes it out of the `status-icons` list first — a shell told to load a plugin
that is gone logs a warning on every start — and then out of the plugin
directory.

Both go back to what was there before, from a record rather than a guess.
The list through `battctl unlist`, which restores what battctl wrote down
before its first change (see [battery](../battery/README.md#what-it-touches)):
an unset key is reset, a list somebody had comes back exactly. The two files
through the install record `install.sh` writes before `make install`, in
`~/.config/furios-battery-time/install-record/` (reading `/usr/lib` needs no
root): removed where nothing was, somebody else's file put back where there
was one, and left alone — with a message — where they changed since. An
install from before 30.9.2026 has no record and is removed by name, as
before, and `uninstall.sh` says so.
