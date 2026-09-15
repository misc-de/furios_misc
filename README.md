# furios_misc — Kleinigkeiten fuer das FuriPhone FLX1

Eine Sammelstelle. Was hier liegt, ist zu klein fuer ein eigenes Repo und zu
nuetzlich, um es wegzuwerfen: einzelne Programme, die je eine Sache am
Telefon in Ordnung bringen, ohne einen Bestandteil von FuriOS zu patchen
oder zu ersetzen.

Die groesseren Baustellen wohnen anderswo — [furios_pipewire][a] (Audio),
[furios_modem_fixes][m] (Mobilfunk), [furios_gps][g] (Ortung),
[furios_killswitch][k] (die drei Schalter am Gehaeuse) — und bedient werden
sie alle aus derselben App, [furios_app][p].

[a]: https://github.com/misc-de/furios_pipewire
[m]: https://github.com/misc-de/furios_modem_fixes
[g]: https://github.com/misc-de/furios_gps
[k]: https://github.com/misc-de/furios_killswitch
[p]: https://github.com/misc-de/furios_app

## Was drin ist

| | | |
|---|---|---|
| [battery](battery/) | `battctl` | Das Akkusymbol faerbt sich: die Huelle nach der Ladeleistung, die Fuellung nach dem Ladestand |

Jedes Verzeichnis steht fuer sich: eigenes README, eigener `install.sh`,
eigene Tests.

```
git clone https://github.com/misc-de/furios_misc
cd furios_misc/battery && ./install.sh
```

## Hausordnung

Damit die Sammlung eine Sammlung bleibt und kein Haufen:

- **Ein Verzeichnis, eine Sache.** Mit `README.md` (was und warum),
  `install.sh` und `tests/`. Was gemessen wurde und was dabei ueberrascht
  hat, gehoert in ein `FINDINGS.md` daneben — das ist meistens der
  eigentliche Wert.
- **Nichts wird gepatcht.** Wer einen Bestandteil von FuriOS ersetzen muss,
  ist hier falsch und gehoert in ein eigenes Repo mit einem Weg zurueck.
- **SPDX-Kopf in jede Datei**, MIT (siehe LICENSE), und ein `NOTICE`, wo zur
  Laufzeit fremder Code mitspielt.
- **Ein Weg zurueck.** Was etwas veraendert, kann es auch zuruecknehmen —
  `uninstall.sh`, oder ein Unterbefehl, der den Auslieferungszustand
  wiederherstellt.
- **Tests laufen auf dem Telefon**, ohne Display, ohne root, ohne
  Fremdpakete. `./run-tests.sh` ruft die aller Unterprojekte auf.

## Tests

```
./run-tests.sh          # alle Unterprojekte - NIE mit sudo
```
