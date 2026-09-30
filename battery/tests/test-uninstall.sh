#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# The invariant, for both halves (battery/ and phosh-battery-time/): after
# install.sh, everything switched on, and uninstall.sh, the home, the runtime
# directory, phosh's plugin directory and the settings are what they were
# before install.sh. Anything the installers or battctl write that the
# uninstallers do not take away shows up here as a path or a key - without
# this test knowing which paths those are.
#
# Everything runs in a sandbox of its own:
#   - a home and a runtime directory of its own;
#   - systemctl is a stub that makes and removes the enable links the way the
#     real one does, and fails like it when there is no user manager;
#   - sudo is a stub that runs only "make ... install|uninstall", with DESTDIR
#     in the sandbox - so the plugin's real Makefile is what is checked;
#   - gsettings writes a key file in the sandbox instead of dconf
#     (GSETTINGS_BACKEND=keyfile), and the memory backend still answers with
#     the shipped defaults.
# Nothing reaches the phone's units, its shell or its settings.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
BATTERY=$(dirname "$HERE")
PLUGIN=$(dirname "$BATTERY")/phosh-battery-time
. "$HERE/lib.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
REAL_PATH=$PATH

missing=
command -v gsettings >/dev/null || missing="$missing gsettings"
gsettings list-schemas 2>/dev/null | grep -qx mobi.phosh.shell.plugins \
    || missing="$missing phosh-schemas"
if [ -n "$missing" ]; then
    printf '  \033[33mskipped\033[0m - install.sh cannot run here, missing:%s\n' "$missing"
    exit 0
fi
with_plugin=yes
{ command -v cc && command -v make && pkg-config --exists phosh-plugins gtk+-3.0; } \
    >/dev/null 2>&1 || with_plugin=

mkdir -p "$TMP/bin"
cat > "$TMP/bin/systemctl" <<'STUB'
#!/bin/bash
echo "$*" >> "$SANDBOX/systemctl.log"
if [ "${SANDBOX_NO_BUS:-}" = 1 ]; then
    echo "Failed to connect to bus: No medium found" >&2; exit 1
fi
user=; verb=; units=()
for a; do
    case $a in
        --user) user=1 ;;
        -*) ;;
        *) if [ -z "$verb" ]; then verb=$a; else units+=("$a"); fi ;;
    esac
done
[ -n "$user" ] || { echo "no system manager in the sandbox" >&2; exit 1; }
dir=$HOME/.config/systemd/user
case $verb in
    enable|disable)
        for u in "${units[@]}"; do
            [ -f "$dir/$u" ] || { echo "Unit file $u does not exist." >&2; exit 1; }
            if [ "$verb" = enable ]; then
                for t in $(sed -n 's/^WantedBy=//p' "$dir/$u"); do
                    mkdir -p "$dir/$t.wants"
                    ln -sf "$dir/$u" "$dir/$t.wants/$u"
                done
            else
                rm -f "$dir"/*.wants/"$u"
            fi
        done ;;
    is-enabled) for u in "${units[@]}"; do ls "$dir"/*.wants/"$u" >/dev/null 2>&1 || exit 1; done ;;
    is-active) exit 3 ;;
esac
exit 0
STUB
cat > "$TMP/bin/sudo" <<'STUB'
#!/bin/bash
echo "$*" >> "$SANDBOX/sudo.log"
if [ "$1" = make ]; then
    shift
    exec make DESTDIR="$SANDBOX/root" "$@"
fi
echo "sudo: only make runs in the sandbox" >&2
exit 1
STUB
chmod +x "$TMP/bin/systemctl" "$TMP/bin/sudo"

# Files and links with their content, and every directory but the generic
# parents install -d makes along the way. The settings key file is looked at
# on its own.
snapshot() {
    (cd "$SANDBOX" || exit 1
     find home run root -path home/.config/glib-2.0 -prune -o -type f -exec md5sum {} + | sort -k2
     find home run root -type l -printf 'link %p -> %l\n' | sort
     find home run root -mindepth 1 -type d -printf 'dir %p\n' | sort \
        | grep -vxE 'dir home/\.local(/bin|/share(/doc)?)?|dir home/\.config(/systemd(/user(/[^/]+\.wants)?)?|/glib-2\.0.*)?|dir root/.*')
}

scenario() {
    # scenario <name> <1 = without a user manager> <yes = the plugin too>
    #          [widget-first = the plugin's uninstall.sh runs first]
    SANDBOX=$TMP/$(echo "$1" | tr -c 'a-z0-9\n' '-')
    export SANDBOX
    mkdir -p "$SANDBOX/home" "$SANDBOX/run" "$SANDBOX/root"
    local before after keys
    before=$(snapshot)
    (
        export HOME=$SANDBOX/home XDG_RUNTIME_DIR=$SANDBOX/run GSETTINGS_BACKEND=keyfile
        export FURIOS_BATTERY_PLUGIN_SO_GLOB="$SANDBOX/root/usr/lib/*/phosh/plugins/libphosh-plugin-furios-battery-time.so"
        unset XDG_CONFIG_HOME XDG_DATA_HOME DBUS_SESSION_BUS_ADDRESS
        unset FURIOS_BATTERY_CONFIG FURIOS_BATTERY_STATE FURIOS_BATTERY_PLUGIN_STATE \
              FURIOS_BATTERY_COLOUR_STATE FURIOS_BATTERY_THEMES
        export PATH=$TMP/bin:$REAL_PATH
        bash "$BATTERY/install.sh" >/dev/null 2>&1 || echo "battery/install.sh failed" >&2
        [ "$3" = yes ] && { bash "$PLUGIN/install.sh" >/dev/null 2>&1 \
            || echo "phosh-battery-time/install.sh failed" >&2; }
        # Everything somebody can switch on, and what the daemon writes while
        # it runs (it is not started here: it would colour the real bar). Its
        # entry in phosh's list is what the daemon adds when it shows a time.
        for option in charging discharging level runtime charge_time; do
            "$HOME/.local/bin/battctl" config "$option" on >/dev/null 2>&1
        done
        systemctl --user enable --now furios-battery-color.service
        gsettings set mobi.phosh.shell.plugins status-icons "['furios-battery-time']"
        echo '{}' > "$HOME/.config/furios-battery/state.json"
        echo '{}' > "$HOME/.config/furios-battery/state.json.new"
        echo '{}' > "$HOME/.config/furios-battery/config.json.new"
        for f in furios-battery-color furios-battery-time; do
            echo x > "$XDG_RUNTIME_DIR/$f"; echo x > "$XDG_RUNTIME_DIR/$f.new"
        done
        mkdir -p "$HOME/.local/bin/__pycache__"
        : > "$HOME/.local/bin/__pycache__/battctlcpython-313.pyc"
        find "$SANDBOX/root" -type f | wc -l > "$SANDBOX/plugin-files"
        # Either order: each uninstall.sh has to put phosh's list back alone.
        if [ "${4:-}" = widget-first ]; then
            bash "$PLUGIN/uninstall.sh" >/dev/null 2>&1 \
                || echo "phosh-battery-time/uninstall.sh failed" >&2
        fi
        SANDBOX_NO_BUS=$2 bash "$BATTERY/uninstall.sh" >/dev/null 2>&1 \
            || echo "battery/uninstall.sh failed" >&2
        if [ "$3" = yes ] && [ "${4:-}" != widget-first ]; then
            bash "$PLUGIN/uninstall.sh" >/dev/null 2>&1 \
                || echo "phosh-battery-time/uninstall.sh failed" >&2
        fi
    )
    after=$(snapshot)
    [ "$3" = yes ] && check "$1: the plugin (.so and .plugin) went into phosh's directory" \
        "2" "$(tr -d ' ' < "$SANDBOX/plugin-files")"
    check "$1: everything is as before install.sh" "" \
        "$(diff <(echo "$before") <(echo "$after") | grep '^[<>]')"
    keys=$(grep -v '^\[' "$SANDBOX/home/.config/glib-2.0/settings/keyfile" 2>/dev/null | grep .)
    check "$1: no setting left changed (reset, not a copy of the default)" "" "$keys"
    check "$1: root only for make install/uninstall" "" \
        "$(grep -vE '^make -C .*phosh-battery-time (install|uninstall)$' "$SANDBOX/sudo.log" 2>/dev/null)"
}

scenario "battctl alone" "" ""
scenario "battctl alone, without a user manager (ssh)" 1 ""
if [ -n "$with_plugin" ]; then
    scenario "battctl and the widget" "" yes
    scenario "the widget uninstalled first" "" yes widget-first
else
    printf '  \033[33mskipped\033[0m the widget - no compiler or phosh-dev here\n'
fi

summary
