# phosh-battery-time — the time left, as a status icon

A plugin for phosh's top bar. It shows one thing: the time
[`battctl`](../battery/) writes for it — how long the battery lasts, or how
long until it is full — in the shell's own indicator box, in the shell's own
font.

    04:38  🔋

It is one C file. It reads one small file in `$XDG_RUNTIME_DIR`, believes
nothing about it, and does nothing else: every failure is "show nothing",
because this runs **inside phosh's process** and a shell that dies over an
odd battery reading would be a far worse bargain than a missing number.

## Why a plugin and not a window of our own

That is what `battctl` did first, and still does when this is not installed:
a layer-shell strip over the top bar, in the place the percentage is emptied
out of.

It works, and it is invisible exactly when you want it. phoc has no
session-lock protocol, so phosh's lock screen is an ordinary layer surface on
the same `OVERLAY` layer — and within a layer the newest is on top. The lock
screen is created when the phone is locked, which is after us. Measured with
two strips side by side: the one started second covers the first.

A plugin is a widget **inside** phosh's indicator box, so it is drawn wherever
that box is, lock screen included. It inherits that box's font, which is how
it ends up looking like the percentage beside it without a line of CSS. And
nothing has to be taken away from the percentage to make room, so the theme
machinery the strip needs — a stylesheet that empties `phosh-battery-info
label` and holds its width — is not needed at all.

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
after installing, either reboot or:

    systemctl --user restart mobi.phosh.Shell.service

`battctl status` says which way the time is being shown, and what is missing
if it is the other one.

## Switching it on

Nothing here does. `battctl` adds `furios-battery-time` to the shell's
`status-icons` list when **time left** or **charging time** is switched on,
takes it out again when both are off, and writes the time in between. The
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

Needs a display to build a GTK widget on; without one, or without phosh's
headers, it says so and skips.

## Uninstall

    ./uninstall.sh

Takes it out of the `status-icons` list first — a shell told to load a plugin
that is gone logs a warning on every start — and then out of the plugin
directory.
