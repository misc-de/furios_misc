#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Removes everything this project installed, and - first - everything it
# changed or wrote while it ran. The order matters: colour, time and plugin
# list must go back before the program that knows how to put them back is
# deleted. Afterwards a fresh install.sh finds the phone as it finds a new one.
set -uo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Please run WITHOUT sudo." >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
UNIT="$HOME/.config/systemd/user"
DOC="$HOME/.local/share/doc/furios-battery"

systemctl --user disable --now furios-battery-color.service 2>/dev/null
# The enable link by hand as well: without a user manager to talk to (an ssh
# login) "disable" fails, and a link left in gnome-session.target.wants would
# be a colour switched on again the moment a fresh install puts the unit back.
rm -f "$UNIT"/*.wants/furios-battery-color.service

# restore: colour and time gone, our entry out of phosh's plugin list (the key
# reset once the list is the shipped one again), whatever an older version
# did to the themes and the percentage put back, config and state deleted.
# Through the checkout's copy when the installed one is already gone.
if [ -x "$BIN/battctl" ]; then "$BIN/battctl" restore; else "$SRC/battctl" restore; fi

# The widget went in with battctl, so it goes out with it - while battctl and
# its record of phosh's list are still here for the widget's uninstall.sh to
# use. Only one this installer put there (it has an install record);
# somebody's own build of it is theirs to take out.
WIDGET_REC="${XDG_CONFIG_HOME:-$HOME/.config}/furios-battery-time/install-record"
if [ -d "$WIDGET_REC" ] && [ -x "$SRC/../phosh-battery-time/uninstall.sh" ]; then
    "$SRC/../phosh-battery-time/uninstall.sh"
fi
# The installed files go back to what install.sh found before its first run,
# from the record it wrote then: gone where nothing was, the earlier file
# where there was one, left alone where somebody changed ours since. Without
# a record - an install from before 30.9.2026 - they are removed by name, as
# uninstall.sh always did, and it says so rather than pretending to know.
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/furios-battery"
REC_DIR="$CONF/install-record"
# shellcheck source=install-record.sh
. "$SRC/install-record.sh"
if rec_exists; then
    rec_restore
else
    echo "No install record (installed before 30.9.2026): removing the files"
    echo "by name - what was at those paths before cannot be known."
    rm -f "$BIN/battctl" "$UNIT/furios-battery-color.service"
    rm -rf "$DOC"
fi

# And what restore leaves to the directory it lives in: the config directory
# itself - the install record with it, unless rec_restore kept it because a
# file from before the install could not be put back (it said where) - and
# the two files in the runtime directory with their temporary siblings (a
# reboot would take those, a reinstall does not wait for one).
if [ -d "$REC_DIR" ]; then
    find "$CONF" -mindepth 1 -maxdepth 1 ! -name install-record -exec rm -rf {} +
else
    rm -rf "$CONF"
fi
run=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
rm -f "$run/furios-battery-color" "$run/furios-battery-color.new" \
      "$run/furios-battery-time" "$run/furios-battery-time.new"

rm -f "$BIN"/__pycache__/battctlcpython-*.pyc
rmdir "$BIN/__pycache__" 2>/dev/null
systemctl --user daemon-reload 2>/dev/null

echo "Removed."
