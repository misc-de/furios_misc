# furios_battery — das Akkusymbol faerbt sich nach der Ladeleistung

Das FuriPhone zeigt beim Laden einen Blitz und eine Prozentzahl. Beides sieht
gleich aus, ob ein Watt hineingeht oder sechs — und genau das ist die Zahl,
die man sehen will: ein muedes Kabel, ein Laptop-Port oder ein Netzteil, das
sich still neu verhandelt hat, sehen alle aus wie „laedt" und kosten Stunden.

Also: **gruen**, wenn es schnell geht, **orange** dazwischen, **rot**, wenn
sich kaum etwas bewegt.

Wahlweise dasselbe im Akkubetrieb, dort mit umgekehrter Bedeutung — gruen ist
ein Telefon, das wenig zieht. Das ist ausgeschaltet, bis man es einschaltet:
eine Farbe, die den ganzen Tag leuchtet, ist keine Nachricht mehr.

```
git clone https://github.com/misc-de/furios_battery
cd furios_battery
./install.sh                 # NIE mit sudo - es braucht gar kein root
systemctl --user enable --now furios-battery-color.service
```

Oder in der App *misc-de* unter **Battery**.

## Wie die Farbe an das Symbol kommt

phosh ist GTK3, und sein Akkusymbol ist der CSS-Knoten `phosh-battery-info`.
Eine Zeile CSS faerbt es:

```css
phosh-battery-info image { color: #2ec27e; }
```

Der naheliegende Ort dafuer ist `~/.config/gtk-3.0/gtk.css` — und der ist eine
Sackgasse: GTK3 liest die Datei **einmal beim Programmstart** und nie wieder.
Eine Farbe, die sich aendert, braeuchte also bei jedem Wechsel einen Neustart
der Shell, und das ist auf diesem Telefon das Einzige, was man nicht tut.

Was GTK3 zur Laufzeit sehr wohl neu liest, ist das **Theme**. Ein
`gsettings set org.gnome.desktop.interface gtk-theme …` restyled jede
laufende GTK-3-Anwendung binnen einer Sekunde, phosh eingeschlossen. Dieses
Projekt schreibt deshalb drei Themes, die nichts weiter sind als das Theme
des Nutzers plus jene eine Zeile:

```
~/.themes/adw-gtk3-batt-green/gtk-3.0/gtk.css
    @import url("file:///usr/share/themes/adw-gtk3/gtk-3.0/gtk.css");
    phosh-battery-info image { color: #2ec27e; }
```

…und schaltet zwischen ihnen um.

**Was das kostet** — das gehoert vor die Entscheidung, nicht dahinter: jeder
Wechsel restyled kurz alle GTK-3-Anwendungen, und die Theme-Einstellung zeigt
solange einen unserer Namen. Es passiert beim Farbwechsel, nicht laufend: ein
paar Mal pro Ladung. Wer sein Theme selbst umstellt, wird nicht ueberstimmt —
der Dienst merkt es, baut auf dem neuen auf und traegt die Farbe hinueber.

## Schwellen

| | gruen | orange | rot |
|---|---|---|---|
| Laden | ab 7 W | ab 3 W | darunter |
| Entladen | bis 1 W | bis 3 W | darueber |

Die Werte sind **vorlaeufig** und sollen korrigiert werden, sobald einmal eine
ganze Ladung mitgesehen wurde; siehe FINDINGS.md. Das Telefon handelt ueber
USB-PD 12,7 W aus, gemessen wurden bisher hoechstens 5,9 W.

```
battctl config charge-green-w 6
battctl config discharging on
battctl config                  # alles, was es gibt
```

Damit die Farbe nicht auf dem Rauschen flackert — `current_now` springt um ein
Viertel Ampere zwischen zwei Messungen — entscheidet nicht der letzte Wert,
sondern der **Median** einer Minute; eine Schwelle muss um ein Zehntel
ueberschritten werden, bevor die Farbe folgt, und jede Farbe bleibt
mindestens 45 Sekunden stehen.

## Was es anfasst

Nichts, wofuer es root braeuchte. Es liest drei Dateien unter
`/sys/class/power_supply/battery`, schreibt `~/.themes` und setzt einen
gsettings-Schluessel. `battctl restore` nimmt alles davon zurueck,
`./uninstall.sh` zusaetzlich das Programm.

Der Taktgeber ist **UPower**: es fragt den Akku ohnehin fuer das ganze
Telefon ab, also wird sein Signal abonniert, statt selbst zu pollen. Ein
langsamer Zeitgeber (120 s) laeuft als Netz darunter mit.

## Tests

```
tests/run-tests.sh      # ohne Display, ohne Akku, ohne root - NIE mit sudo
tests/coverage.sh
```

82 Tests, 90,8 % der Zeilen. Was fehlt, ist die D-Bus-Verdrahtung des Daemons
— die wird am Geraet belegt, nicht simuliert (FINDINGS.md).
