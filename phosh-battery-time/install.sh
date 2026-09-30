#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Builds the status icon and puts it where phosh looks for plugins. Run it
# WITHOUT sudo - the two lines that write to /usr/lib ask for themselves.
#
# Why this one needs root when the rest of this project does not: phosh takes
# its plugin directory from a compile-time constant (PHOSH_PLUGINS_DIR), so
# there is no directory in the home the shell would look in. Checked against
# phosh 0.55.
set -euo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Please run WITHOUT sudo - only the install step needs root." >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

missing=()
command -v cc >/dev/null || missing+=("a C compiler (apt install build-essential)")
command -v make >/dev/null || missing+=("make (apt install build-essential)")
pkg-config --exists phosh-plugins 2>/dev/null \
    || missing+=("phosh's plugin headers (apt install phosh-dev)")
pkg-config --exists gtk+-3.0 2>/dev/null \
    || missing+=("GTK 3 headers (apt install libgtk-3-dev)")
if [ ${#missing[@]} -gt 0 ]; then
    printf 'Missing: %s\n' "${missing[@]}" >&2
    echo "Nothing was built." >&2
    exit 1
fi

echo "1) building"
make -C "$SRC" all

echo "2) installing"
DIR=$(pkg-config --variable=status_icons_plugins_dir phosh-plugins)
# What phosh's plugin directory held at our two paths before the first
# install, written down before make writes there - so that uninstall.sh puts
# exactly that back (install-record.sh explains the record). In the home:
# reading /usr/lib needs no root, and the record is this user's install.
# DESTDIR only for the tests, which install into a sandbox.
REC_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/furios-battery-time/install-record"
# shellcheck source=install-record.sh
. "$SRC/install-record.sh"
TARGETS=("${DESTDIR:-}$DIR/libphosh-plugin-furios-battery-time.so"
         "${DESTDIR:-}$DIR/furios-battery-time.plugin")
for t in "${TARGETS[@]}"; do rec_before "$t" furios-battery-time; done
sudo make -C "$SRC" install DESTDIR="${DESTDIR:-}"
for t in "${TARGETS[@]}"; do rec_after "$t"; done
echo
echo "Installed in $DIR."
# Installed, not switched on: the icon appears when battctl's "time left" or
# "charging time" is switched on, and that is a decision somebody makes.
echo "It colours the battery and shows a time once battctl has something to"
echo "show - switch an option on in the app under \"Battery\", or e.g.:"
echo "battctl config charging on"
echo
# phosh scans its plugin directory once, when the shell starts. A plugin put
# there afterwards is found by nobody until then, and the shell says so in
# one line: "Custom status-icon 'furios-battery-time' not found".
#
# And there is no shortcut: mobi.phosh.Shell.service is RefuseManualStart and
# RefuseManualStop (measured: "Operation refused, unit ... may be requested by
# dependency only"), and taking the shell down by hand takes the whole session
# with it - OnFailure=gnome-session-shutdown.target, replace-irreversibly.
echo "phosh looks for plugins only when it starts, so this one is picked up"
echo "at the next reboot. There is no way to restart the shell on its own:"
echo "its unit refuses a manual start, and killing it ends the session."
