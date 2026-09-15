# furios_misc — small things for the FuriPhone FLX1

A collection. What lives here is too small for a repository of its own and
too useful to throw away: single programs that each put one thing right on
the phone, without patching or replacing any part of FuriOS.

The larger building sites live elsewhere — [furios_pipewire][a] (audio),
[furios_modem_fixes][m] (cellular), [furios_gps][g] (location),
[furios_killswitch][k] (the three switches on the case) — and all of them are
operated from the same app, [furios_app][p].

[a]: https://github.com/misc-de/furios_pipewire
[m]: https://github.com/misc-de/furios_modem_fixes
[g]: https://github.com/misc-de/furios_gps
[k]: https://github.com/misc-de/furios_killswitch
[p]: https://github.com/misc-de/furios_app

## What is in here

| | | |
|---|---|---|
| [battery](battery/) | `battctl` | The battery icon takes colour: the frame from the charging power, the filling from the charge level |

Each directory stands on its own: its own README, its own `install.sh`, its
own tests.

```
git clone https://github.com/misc-de/furios_misc
cd furios_misc/battery && ./install.sh
```

## House rules

So that the collection stays a collection and does not become a heap:

- **One directory, one thing.** With a `README.md` (what and why), an
  `install.sh` and `tests/`. What was measured and what surprised us belongs
  in a `FINDINGS.md` next to it — that is usually the real value.
- **Nothing is patched.** Anybody who has to replace a part of FuriOS is in
  the wrong place here and belongs in a repository of their own, with a way
  back.
- **An SPDX header in every file**, MIT (see LICENSE), and a `NOTICE`
  wherever somebody else's code plays a part at runtime.
- **A way back.** Whatever changes something can take it back again —
  `uninstall.sh`, or a subcommand that restores the shipped state.
- **Tests run on the phone**, without a display, without root, without
  third-party packages. `./run-tests.sh` calls those of every subproject.

## Tests

```
./run-tests.sh          # every subproject - NEVER with sudo
```
