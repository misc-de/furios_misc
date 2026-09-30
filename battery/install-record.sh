# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# shellcheck shell=bash
#
# What an installation found before it wrote, so that uninstall.sh can put
# exactly that back instead of guessing. Sourced by install.sh and
# uninstall.sh, never run on its own.
#
# The rule it serves: before the FIRST change, write down what was there; on
# uninstall, restore from that note - and only where the file is still the
# one we put there. A file somebody edited after us is theirs now; it stays,
# and the uninstall says so.
#
# The record lives in $REC_DIR (the caller sets it) and is one manifest:
#
#   <original> TAB <sha256 of what we installed last> TAB <path>
#
# <original> is one of
#   absent   nothing was at <path> before the first install: uninstall removes
#            the file again.
#   saved    a file that is not ours was there. A copy is kept in
#            $REC_DIR/saved/ and uninstall puts it back.
#   unknown  a file of ours was already there, from an install made before
#            records existed: what was there before THAT cannot be known any
#            more. Uninstall falls back to what it always did - it removes
#            the file - and says that it had no record.
#   dir      (with "-" as checksum) a directory we created: removed again
#            when it is empty. One that existed before gets no line at all.
#
# A second install never replaces a line's <original>: it only updates the
# checksum, because the file it wrote is the one uninstall must recognise.
#
# $REC_SUDO is put in front of every command that writes a target ("" for
# the home, "sudo" for /usr/lib).

REC_SUDO=${REC_SUDO:-}

# A command, through $REC_SUDO when it is set.
_rec_run() {
    if [ -n "$REC_SUDO" ]; then "$REC_SUDO" "$@"; else "$@"; fi
}

_rec_manifest() { printf '%s/manifest' "$REC_DIR"; }

# The line for one path, or nothing.
# Safe under set -e: a manifest that does not exist yet is no line, not an
# error that ends the install.sh sourcing this.
_rec_line() {
    local m
    m=$(_rec_manifest)
    [ -f "$m" ] || return 0
    awk -F'\t' -v p="$1" '$3 == p { print; exit }' "$m"
}

# A file name for the saved copy that cannot collide and needs no escaping.
_rec_key() { printf '%s' "$1" | sha256sum | cut -c1-32; }

_rec_sum() { sha256sum < "$1" 2>/dev/null | cut -d' ' -f1; }

# Replace (or add) the line for <path>, keeping every other line.
_rec_put() {
    local orig=$1 sum=$2 path=$3 m
    m=$(_rec_manifest)
    { if [ -f "$m" ]; then awk -F'\t' -v p="$path" '$3 != p' "$m"; fi
      printf '%s\t%s\t%s\n' "$orig" "$sum" "$path"; } > "$m.new"
    mv "$m.new" "$m"
}

# rec_before <path> <mark>
# Before the first write to <path>: note whether something was there, and
# keep a copy when it is somebody else's. <mark> is a string every version of
# our own file contains - that is how an install from before records existed
# is told apart from a file that was never ours.
rec_before() {
    local path=$1 mark=$2 orig
    mkdir -p "$REC_DIR"
    chmod 700 "$REC_DIR"
    [ -n "$(_rec_line "$path")" ] && return 0      # the first note stands
    if [ ! -e "$path" ] && [ ! -L "$path" ]; then
        orig=absent
    # -a and the C locale: a shared object is binary, and grep in a UTF-8
    # locale finds nothing in it.
    elif LC_ALL=C grep -aqF -- "$mark" "$path" 2>/dev/null; then
        orig=unknown
    else
        orig=saved
        mkdir -p "$REC_DIR/saved"
        cp -p "$path" "$REC_DIR/saved/$(_rec_key "$path")"
    fi
    _rec_put "$orig" "-" "$path"
}

# rec_after <path>
# After the write: the checksum of what we put there, so that uninstall can
# tell our file from one somebody changed since.
rec_after() {
    local path=$1 line
    line=$(_rec_line "$path")
    [ -n "$line" ] || return 0
    _rec_put "$(printf '%s' "$line" | cut -f1)" "$(_rec_sum "$path")" "$path"
}

# rec_install <mode> <src> <dst> <mark> - the common case in one call.
rec_install() {
    rec_before "$3" "$4"
    _rec_run install -Dm"$1" "$2" "$3"
    rec_after "$3"
}

# rec_dir <dir> - a directory of our own; noted only if we create it.
rec_dir() {
    mkdir -p "$REC_DIR"
    chmod 700 "$REC_DIR"
    [ -n "$(_rec_line "$1")" ] && return 0
    [ -d "$1" ] && return 0
    _rec_put dir "-" "$1"
}

rec_exists() { [ -f "$(_rec_manifest)" ]; }

# rec_restore
# Puts back what the manifest says, newest line first, and reports every
# place where it did not. Afterwards the record is gone - unless a saved
# copy could not be put back, in which case the copy and its line stay and
# the path is printed, so that nothing somebody had is lost.
rec_restore() {
    local m orig sum path keep=() line
    m=$(_rec_manifest)
    [ -f "$m" ] || return 1
    while IFS=$'\t' read -r orig sum path; do
        [ -n "$path" ] || continue
        line=$(printf '%s\t%s\t%s' "$orig" "$sum" "$path")
        if [ "$orig" = dir ]; then
            rmdir "$path" 2>/dev/null \
                || { [ -d "$path" ] && echo "kept $path: not empty - somebody put something there"; }
            continue
        fi
        if [ ! -e "$path" ] && [ ! -L "$path" ]; then
            if [ "$orig" = saved ]; then
                echo "$path is gone since the install - the file that was there before is kept in $REC_DIR/saved"
                keep+=("$line")
            fi
            continue
        fi
        if [ "$sum" != "-" ] && [ "$(_rec_sum "$path")" != "$sum" ]; then
            echo "left $path as it is: changed since the install, so it is not ours any more"
            [ "$orig" = saved ] && keep+=("$line") \
                && echo "  (what was there before the install is kept in $REC_DIR/saved)"
            continue
        fi
        case $orig in
            absent)  _rec_run rm -f "$path" ;;
            unknown) _rec_run rm -f "$path"
                     echo "removed $path: installed before install records existed, so what was there before is not known" ;;
            saved)   _rec_run cp -p "$REC_DIR/saved/$(_rec_key "$path")" "$path"
                     echo "put back $path as it was before the install" ;;
        esac
    done < <(tac "$m")
    if [ ${#keep[@]} -gt 0 ]; then
        printf '%s\n' "${keep[@]}" > "$m"
        return 0
    fi
    rm -rf "$REC_DIR"
}
