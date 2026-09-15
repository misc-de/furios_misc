# Was beim Bauen gemessen wurde

Alles hier am FuriPhone FLX1 nachgemessen, FuriOS mit phosh 0.55,
GTK 3.24.52, Kernel 4.19.325.

## 1 · Die Ladeleistung steht im Akku selbst

```
/sys/class/power_supply/battery/current_now   in µA
/sys/class/power_supply/battery/voltage_now   in µV
/sys/class/power_supply/battery/status        Charging | Discharging | Full | Not charging
```

Produkt = Leistung **in den Akku**. Am 15.9.2026 um 14:19 waren das
1,07–1,36 A bei 4,32 V, also **4,6–5,9 W**; zwei Minuten spaeter nur noch
0,23–0,46 A, also **1,0–1,9 W**, und `time_to_full_now` sprang von 49 auf
200 Minuten.

Der Einbruch ist **nicht erklaert**. Nicht thermisch: Akku 36,6 °C und
fallend, `sw_jeita` = 0, keine Thermalzone ueber 45 °C. Ladestand 76 %, fuer
die CV-Phase zu frueh. Bleiben Netzteil, Kabel oder eine stille
Neuverhandlung. Wer die Schwellen ernst nimmt, sollte deshalb erst eine ganze
Ladung mitschneiden, bevor er 7 W fuer „schnell" haelt.

Die Momentanwerte schwanken um **±0,3 A** von Sekunde zu Sekunde. `current_avg`
des Treibers glaettet, haengt aber lange nach (0,84 → 0,45 A in einer Minute).
Deshalb hier: eigener Median ueber eine Minute.

## 2 · Wandseitig laesst sich nichts messen

- Kernel 4.19 hat die `usb_power_delivery`-Klasse noch nicht — kein
  ausgehandelter Vertrag, keine VBUS-Stromstaerke.
- `/sys/devices/platform/charger/{input_current,chg1_current,chg2_current}`
  liefern alle `4294967295` (0xFFFFFFFF, „nicht gesetzt") und sind wertlos.
- Brauchbar sind nur `ADC_Charger_Voltage` = **4587 mV** (also 5-V-Vertrag)
  und `pdc_max_watt` = **12684000** µW = **12,68 W** als ausgehandeltes
  Maximum. Der Akku nahm davon zeitweise ein Achtel.
- `/sys/class/typec/port0/power_operation_mode` sagt `usb_power_delivery`.

## 3 · Ein Treiberfehler, ueber den man bei der Akkugesundheit stolpert

```
charge_full         4370000 µAh
charge_full_design   437000 µAh     <- Faktor 10 zu klein
```

Deshalb behauptet upower `energy-full-design: 1,89 Wh` und `capacity: 100 %`.
Der Gesundheitswert von upower ist auf diesem Telefon **bedeutungslos**. Die
echten Zahlen: 4370 mAh, 205 Ladezyklen.

## 4 · Die Sackgasse: ~/.config/gtk-3.0/gtk.css

GTK3 liest die Nutzerdatei **einmal beim Start** des Programms. Zwei
Messungen:

- Die Datei existierte hier gar nicht, als phosh startete — phosh hat also
  ueberhaupt keinen User-Provider. Angelegt, drei Sekunden gewartet,
  Screenshot: unveraendert.
- Auch mit Datei wuerde jede Aenderung erst beim naechsten Start wirken. Fuer
  eine Farbe, die sich stuendlich aendert, hiesse das: Shell neustarten, und
  das ist auf diesem Telefon die eine Sache, die man nicht tut
  (`OnFailure=gnome-session-shutdown`).

## 5 · Was live wirkt: der Theme-Name

`gsettings set org.gnome.desktop.interface gtk-theme <name>` schlaegt sofort
durch. Am Geraet mit Screenshots belegt (`grim`, das ueber
zwlr_screencopy auf phoc funktioniert — Paket `grim`, nicht vorinstalliert):

1. Ausgangslage: Symbol weiss.
2. Theme `furios-batt-test` (adw-gtk3 + `color: #ff00ff` auf
   `phosh-battery-info, … image, … label`) → Symbol **und** Prozentzahl
   magenta, **ohne** phosh anzufassen.
3. Theme `furios-batt-test2` mit `phosh-battery-info image { color: #2ec27e }`
   → Symbol gruen, Prozentzahl bleibt weiss. Der Wechsel von einem eigenen
   Theme zum naechsten wirkt genauso — es ist also wiederholbar, nicht nur
   „einmal etwas anderes".
4. Zurueck auf `adw-gtk3` → wieder weiss.

Der CSS-Knoten heisst `phosh-battery-info`. Gefunden nicht im Inspector
(der braeuchte einen Neustart der Shell), sondern in den Ressourcen:

```
gresource list /usr/libexec/phosh | grep css
gresource extract /usr/libexec/phosh /mobi/phosh/stylesheet/common.css
strings /usr/libexec/phosh | grep phosh-battery
```

## 5a · Das Symbol hat zwei Pfade, und einer blieb weiss

Am Geraet gesehen, nachdem die erste Fassung lief: Huelle und Blitz rot, die
**Fuellung weiss**. Das Adwaita-SVG erklaert es:

```
<path class="success" d="m 5 7 v 6 h 3 …" fill="#33d17a"/>   <- der Ladestand
<path d="m 7 0 c -1 0 …" fill="#2e3434"/>                     <- Huelle+Blitz
```

`color` faerbt nur den zweiten. Der erste kommt aus GTK3s Symbol-Palette und
wird mit `-gtk-icon-palette: success …, warning …, error …` gesetzt. Kopflos
nachgewiesen (`Gtk.IconInfo.load_symbolic`): mit success=rot sind 112 von 112
deckenden Pixeln rot, mit success=weiss bleiben genau 24 weiss - das ist die
Fuellung. `Gtk.CssProvider` nimmt die Eigenschaft ohne Parsefehler an.

Alle drei Palettennamen bekommen dieselbe Farbe: unter 20 % ist die Fuellung
`warning` bzw. `error` statt `success`, und ein Symbol, das aussen gruen und
innen rot ist, liest sich als Stoerung und nicht als Ladestand.

## 5b · GTK3 merkt sich ein Theme nach NAMEN, nicht nach Datei

`gtk_css_provider_get_named()` haelt geladene Themes in einer statischen
Tabelle, fuer die Lebensdauer des Prozesses, ohne die Datei erneut anzusehen.
Die Regel zu aendern und den Namen zu behalten heisst also: die Datei auf der
Platte ist richtig, phosh zeigt bis zum naechsten Neustart die alte Fassung,
und nichts sagt warum. Der Theme-Name traegt deshalb vier Zeichen aus einem
SHA-1 der Regel (`adw-gtk3-batt5ae1-green`). Aeltere Generationen werden beim
Schreiben mit entfernt, damit sich nicht pro Aktualisierung ein Verzeichnis
ansammelt.

## 6 · Die Falle, die das ganze Telefon umgefaerbt haette

GTK3 nimmt `gtk-dark.css`, wenn es die Datei gibt und die Sitzung dunkel
bevorzugt. Ein generiertes Theme, das ein `gtk-dark.css` anlegt, obwohl das
Basis-Theme keines hat, legt damit im Dunkelmodus das **helle** Blatt unter
die Oberflaeche — die Farbe stimmte, und das Telefon saehe anders aus.
`write_themes` schreibt das dunkle Blatt deshalb nur, wenn das Basis-Theme
eines hat, und loescht es wieder, wenn es verschwindet. Test:
`test_ohne_dunkles_blatt_wird_keines_erfunden`.

## 7 · Zwei Fallen im eigenen Werkzeug

- **`python3 -m trace` + `unittest.main()` = „Ran 0 tests"**, still, mit
  Rueckgabewert 0 und einem Abdeckungsbericht von 16 %. `unittest.main()`
  sucht Tests in `sys.modules["__main__"]`, und unter dem Tracer ist das der
  Tracer. Die Suite wird deshalb von Hand aus `globals()` gebaut (dieselbe
  Loesung wie in furios_app).
- **Die Abdeckung hat einen Test entlarvt, der aus dem falschen Grund
  bestand**: `test_wartezeit_haelt_die_farbe` sprang von 5,2 W auf 8,6 W und
  erwartete, dass die Wartezeit den Wechsel bremst. Der Median der beiden
  Messungen lag bei 6,9 W, die Hysterese verlangte 7,7 W — die Farbe blieb,
  weil sie ohnehin dieselbe war, und die Wartezeit wurde nie erreicht. Die
  Zeile `return False` blieb unerreicht und hat es verraten.

## 7a · Die Schwellen sind noch nicht gemessen

Die Vorgaben (laden 7/3 W, entladen 3/5 W) sind geraten und als vorlaeufig
gekennzeichnet. `battctl watch` schreibt die Messreihe mit und nennt am Ende
Median, p90, p98 und Maximum, getrennt nach Laden und Entladen.

Fuer den Akkubetrieb zaehlt dabei ausdruecklich der Verbrauch mit
**eingeschaltetem Bildschirm**: das Symbol sieht nur, wer hinschaut, also ist
"normal" das, was das Telefon im Gebrauch zieht, und nicht die Ruhelast auf
dem Tisch. Die Mitschrift fuehrt deshalb eine Spalte mit.

Was dafuer NICHT taugt, beides hier gemessen: `loginctl … IdleHint` stand bei
ausgeschaltetem Bildschirm auf `no`, und `/sys/class/leds/lcd-backlight/
brightness` behielt seinen letzten Wert (629 von 2047). Ein verlaesslicher
Anzeiger war nur, dass `grim` bei dunklem Bildschirm mit
`failed to copy output HWCOMPOSER-1` scheitert - fuer eine Messreihe absurd,
also steht der Rohwert in der Spalte und wer die Reihe auswertet, entscheidet.

## 8 · Was hier NICHT geprueft ist

Die D-Bus-Verdrahtung des Daemons (UPower-Abo, Signalbehandlung,
Hauptschleife) hat keine Tests — ein Abo laesst sich schlecht simulieren, und
ein simuliertes waere kein Beleg. Es wird am Geraet belegt: Dienst starten,
Kabel ziehen, Kabel stecken, Journal und Screenshot.

Dazu die Warnung aus einem Nachbarprojekt, die hier eingebaut ist: ein Abo,
dessen Verbindung eingesammelt wird, verfaellt **still** — kein Fehler, kein
Journaleintrag, ein gesund aussehender Dienst, der nie wieder misst. Der
Proxy wird deshalb festgehalten, und der 120-s-Zeitgeber laeuft als Netz
darunter.
