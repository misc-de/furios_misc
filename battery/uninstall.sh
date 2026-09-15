#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Removes everything this project installed, and - first - everything it
# changed. The order matters: the themes must go back before the program that
# knows how to put them back is deleted.
set -uo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Bitte OHNE sudo ausfuehren." >&2
    exit 1
fi

BIN="$HOME/.local/bin"
UNIT="$HOME/.config/systemd/user"
DOC="$HOME/.local/share/doc/furios-battery"

systemctl --user disable --now furios-battery-color.service 2>/dev/null
[ -x "$BIN/battctl" ] && "$BIN/battctl" restore

rm -f "$BIN/battctl" "$UNIT/furios-battery-color.service"
rm -rf "$DOC"
systemctl --user daemon-reload

echo "Entfernt. Theme: $(gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null)"
