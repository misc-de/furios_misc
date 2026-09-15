# battery — das Akkusymbol sagt, was es weiss

Das FuriPhone zeigt beim Laden einen Blitz und eine Prozentzahl. Beides sieht
gleich aus, ob ein Watt hineingeht oder sechs — und genau das ist die Zahl,
die man sehen will: ein muedes Kabel, ein Laptop-Port oder ein Netzteil, das
sich still neu verhandelt hat, sehen alle aus wie „laedt" und kosten Stunden.

Das Symbol besteht aus zwei Teilen, und die sagen ab jetzt zwei
verschiedene Dinge:

| | was es sagt | |
|---|---|---|
| **Huelle und Blitz** | wie schnell sich der Akku bewegt | gruen · orange · rot |
| **Fuellung** | wie voll er ist | schlicht · orange · rot |

Also: **gruen**, wenn viel hineingeht, **orange** dazwischen, **rot**, wenn
sich kaum etwas bewegt — und die Fuellung darin faerbt sich unabhaengig
davon, wenn der Ladestand knapp wird.

Die Farbe der Huelle im Akkubetrieb ist ausgeschaltet, bis man sie
einschaltet; die Fuellung faerbt sich immer, weil ein fast leerer Akku das
sagen soll, ob er nun laedt, entlaedt oder voll ist.

Eine wackelnde Verbindung — defekte Buchse, mueder Stecker — laesst das
Telefon zwischen Laden und Entladen springen. Der Huelle folgt das **nicht**:
sie bleibt farblos, solange sich die Messungen einer Minute nicht ueber die
Richtung einig sind. Sonst waere die Farbe eine Anzeige des Kabels.

**Zwei Einschraenkungen, die vom Symbol kommen, nicht von uns** (Details in
FINDINGS.md): Adwaitas Entlade-Symbole bestehen aus EINEM Pfad — dort gibt
es keine zwei Haelften, und die dringlichere der beiden Farben bekommt das
ganze Symbol. Und wenn Kernel und UPower sich ueber die Richtung
widersprechen, bleibt die Huelle farblos, weil phosh dann ein Symbol
zeichnet, zu dem die Farbe nicht passt.

```
git clone https://github.com/misc-de/furios_misc
cd furios_misc/battery
./install.sh                 # NIE mit sudo - es braucht gar kein root
systemctl --user enable --now furios-battery-color.service
```

Oder in der App *misc-de* unter **Battery**.

## Wie die Farbe an das Symbol kommt

phosh ist GTK3, und sein Akkusymbol ist der CSS-Knoten `phosh-battery-info`.
Eine Zeile CSS faerbt es:

```css
phosh-battery-info image {
  color: #e01b24;                                  /* Huelle: 1 W gehen rein */
  -gtk-icon-palette: success #ff7800, warning #ff7800, error #ff7800;
}                                                  /* Fuellung: unter 60 %   */
```

Zwei Deklarationen, weil das Symbol aus **zwei Pfaden** besteht: Huelle und
Blitz folgen `color`, die Fuellung traegt im Adwaita-SVG `class="success"`
und kommt aus der Symbol-Palette. Ohne die zweite Zeile bleibt die Fuellung
weiss in einem roten Akku.

Alle drei Palettennamen bekommen dieselbe Farbe, weil die Fuellung unter
20 % `warning` bzw. `error` heisst — die Farbe soll vom Ladestand kommen und
nicht davon, welche Datei phosh gerade gegriffen hat.

Fehlt eine der beiden Aussagen, fehlt die Zeile: ein Regelwerk ohne `color`
laesst die Huelle in der Farbe der Leiste, eines ohne Palette die Fuellung.
Ein „weiss" hinzuschreiben hiesse, einen Vordergrund zu raten, den wir nicht
lesen koennen.

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
~/.themes/adw-gtk3-batt7e17-red-amber/gtk-3.0/gtk.css
    @import url("file:///usr/share/themes/adw-gtk3/gtk-3.0/gtk.css");
    phosh-battery-info image { color: …; -gtk-icon-palette: …; }
```

Der Name traegt beide Haelften, weil beide in derselben Datei stehen. Die
Kombinationen werden erst geschrieben, wenn sie gebraucht werden — zwoelf
Verzeichnisse in `~/.themes` waeren zwoelf Eintraege in jeder Theme-Auswahl
auf dem Telefon.

Die vier Zeichen im Namen sind die Kennung der Regel. Sie stehen dort, weil
GTK3 ein benanntes Theme **fuer die Lebensdauer des Prozesses** zwischen-
speichert, nach Namen und ohne zweiten Blick auf die Datei: aendert man die
Regel und behaelt den Namen, zeigt phosh bis zum naechsten Neustart weiter
die Fassung von damals.

…und schaltet zwischen ihnen um.

**Was das kostet** — das gehoert vor die Entscheidung, nicht dahinter: jeder
Wechsel restyled kurz alle GTK-3-Anwendungen, und die Theme-Einstellung zeigt
solange einen unserer Namen. Es passiert beim Farbwechsel, nicht laufend: ein
paar Mal pro Ladung. Wer sein Theme selbst umstellt, wird nicht ueberstimmt —
der Dienst merkt es, baut auf dem neuen auf und traegt die Farbe hinueber.

## Schwellen

| | schlicht | gruen | orange | rot |
|---|---|---|---|---|
| Huelle, Laden | — | ab 7 W | ab 3 W | darunter |
| Huelle, Entladen | unter 3 W | — | ab 3 W | ab 5 W |
| Fuellung | ueber 60 % | — | unter 60 % | unter 15 % |

Im Akkubetrieb ist **weiss der Normalfall**: ein Telefon, das tut, was ein
Telefon tut, sagt nichts, und nur ein ungewoehnlicher Verbrauch meldet sich.
Gruen gibt es dort nicht - eine Farbe, die den ganzen Tag leuchtet, ist keine
Nachricht mehr.

Die Werte sind **vorlaeufig**. Sie gehoeren gemessen, nicht geraten - dafuer
gibt es `battctl watch`:

```
battctl watch 3600 --csv ~/verbrauch.csv     # eine Stunde mitschreiben
```

Am Ende stehen Median, p90, p98 und Maximum, getrennt nach Laden und
Entladen. Ein brauchbarer Anfang ist **orange bei p90, rot bei p98**: dann
meldet sich das gewoehnliche Zehntel und der Rest bleibt weiss.

Wichtig dabei: fuer den Akkubetrieb zaehlt der Verbrauch mit **einge-
schaltetem Bildschirm**. Dieses Symbol sieht nur, wer auf den Bildschirm
schaut - die 0,2 W eines Telefons auf dem Tisch sind keine sinnvolle Basis.
Die Mitschrift traegt deshalb den Wert der Hintergrundbeleuchtung mit.

Das Telefon handelt ueber USB-PD 12,7 W aus, gemessen wurden bisher
hoechstens 5,9 W - auch die Ladeschwellen sind also noch nicht bestaetigt.

```
battctl config charge-green-w 6
battctl config drain-amber-w 2.5
battctl config discharging on
battctl config level-amber-pct 50
battctl config level off        # Fuellung gar nicht faerben
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

127 Tests, 89,3 % der Zeilen. Was fehlt, ist die D-Bus-Verdrahtung des Daemons
— die wird am Geraet belegt, nicht simuliert (FINDINGS.md).
