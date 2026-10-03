# Erste Schritte

Diese Anleitung macht aus dem mitgelieferten Beispielscan eines Halters eine STEP-Datei. Sie
dauert etwa 20 Minuten und verwendet die wichtigsten Werkzeuge je einmal. Die englische
Fassung ist [getting-started.md](getting-started.md).

Der Halter ist ein L-förmiges Teil mit 80 × 50 × 60 mm, zwei Bohrungen in der Grundplatte,
einer Bohrung im Steg und verrundeten Kanten. Der Scan hat etwa 167.000 Dreiecke und ein
Rauschen von 0,03 mm und liegt wie ein echter Scan schräg im Raum.

## Maus und Tastatur

- Rechte Maustaste ziehen dreht die Ansicht, mittlere Maustaste verschiebt, das Mausrad zoomt
  zum Mauszeiger. Doppelklick mit der mittleren Maustaste zeigt alles.
- Die linke Maustaste wählt aus und malt; sie bewegt nie die Ansicht.
- `F1` öffnet die Hilfeseite des aktiven Werkzeugs, `Strg+/` zeigt alle Tastenkürzel.
- `Eingabe` bestätigt ein Werkzeug (OK), `Esc` bricht es ab. `Strg+Z` macht den letzten
  Schritt rückgängig.

## 1. Beispiel öffnen

1. Mesh-to-CAD starten. Das Ansichtsfenster zeigt _Kein Scan geladen_.
2. **Beispiel öffnen** klicken (oder _Hilfe > Beispiel öffnen: Halter_).
3. Der Bereich _Scan importieren_ zeigt Datei, Abmessungen und das gemessene Scanrauschen.
   Einheit _mm_ und die vorgeschlagene Toleranz beibehalten und **OK** klicken.

Im Projektbaum steht jetzt _Scan_ mit Dateiname und Dreiecksanzahl. Die Statusleiste zeigt die
Dreiecksanzahl und die Projekttoleranz.

## 2. Scan vorbereiten

Arbeitsschritt _Vorbereiten_. **Reparieren** prüft den Scan auf doppelte Punkte, Dreiecke ohne
Fläche und uneinheitliche Orientierung. Das Beispiel hat solche Fehler nicht; der Bereich
meldet, dass nichts zu tun ist. Bei einem echten Scan zuerst reparieren, dann lose Teile mit
_Kleine Teile entfernen_ löschen und kleine Löcher mit _Löcher füllen_ schließen.

## 3. Scan ausrichten

Arbeitsschritt _Ausrichten_, Werkzeug **Automatisch ausrichten**. Die größte Ebene (die
Unterseite der Grundplatte) wird zur XY-Ebene, die größte Ebene senkrecht dazu zur XZ-Ebene,
und der Ursprung liegt an einer Ecke des Scans. Unter _Ergebnis_ prüfen, dass die größte Ebene
höchstens wenige Hundertstel Grad zu XY liegt. Liegt das Teil falsch herum, mit _Umdrehen_
oder _Drehen 90°_ korrigieren und **OK** klicken.

Die Ausrichtung ist der erste Eintrag unter _Verlauf_. Ein Doppelklick öffnet sie zum Ändern;
alle folgenden Schritte werden danach neu berechnet.

## 4. Flächen finden

**Segmentieren** teilt den Scan in Bereiche aus Ebenen, Zylindern und anderen Formen. Sie
erscheinen im Projektbaum unter _Bereiche_, nach Typ gruppiert. Zeigt der Mauszeiger auf einen
Bereich, werden seine Dreiecke im Ansichtsfenster hervorgehoben.

## 5. Bohrungen einpassen

Arbeitsschritt _Modellieren_, Werkzeug **Form einpassen** (`A`).

1. In der Werkzeugleiste _Flächenauswahl_ (`W`) wählen und die Wand einer Bohrung in der
   Grundplatte anklicken.
2. Der Bereich zeigt _Zylinder_ mit Scanrauschen, RMS, Maximum und dem Anteil der Dreiecke in
   der Toleranz. Der Radius wird auf 4,500 mm gefangen und die Achse auf Z; jeder gefangene
   Wert zeigt den gemessenen Wert, den er ersetzt.
3. **OK** klicken. _Zylinder 1_ erscheint im Verlauf, die verwendeten Dreiecke verlassen die
   Auswahl.

Das Gleiche für die zweite Bohrung und die Bohrung im Steg wiederholen (Radius 6,000 mm, Achse
parallel zu Y).

## 6. Seitenprofil skizzieren

Werkzeug **Skizze** (`S`). Ebene _YZ_ wählen und den Schnitt in die Mitte des Teils legen. Der
Schnitt durch den Scan erscheint in der Skizzenebene. **OK** passt Linien und Bögen ein: die
L-förmige Kontur mit der inneren Verrundung R6. Werte werden auf Konstruktionswerte wie
8,000 mm gefangen. Das Profil muss geschlossen sein; Lücken listet der Bereich auf. **Skizze
beenden** klicken.

## 7. Körper extrudieren

Werkzeug **Extrusion** (`E`). _Skizze 1_ und _Symmetrisch_ wählen. Der Abstand wird aus der
Ausdehnung des Scans übernommen (80 mm). _Neuer Körper_ beibehalten und **OK** klicken.
_Körper 1_ erscheint unter _Körper_; Volumen und Gültigkeit stehen in den Eigenschaften, wenn
er ausgewählt ist.

## 8. Bohrungen schneiden und Kanten verrunden

1. Auf der Oberseite der Grundplatte eine Skizze mit zwei Kreisen an den eingepassten
   Bohrungsachsen anlegen und mit _Abziehen_ durch die Grundplatte extrudieren. Ebenso die
   Bohrung im Steg.
2. Werkzeug **Verrundung**: die beiden senkrechten vorderen Kanten der Grundplatte anklicken.
   _Radius aus Scan_ passt einen Zylinder an den Scan entlang der Kanten ein und schlägt
   8,000 mm vor. **OK** klicken.

## 9. Abweichung prüfen

Arbeitsschritt _Prüfen_, Werkzeug **Abweichung** (`D`). Der Scan wird nach seinem Abstand zum
Körper eingefärbt: grün innerhalb der Toleranz, wärmere Farben, wo der Scan außerhalb liegt,
kühlere, wo er innerhalb liegt. Die Legende zeigt den Anteil der Punkte in der Toleranz. Große
farbige Flächen bedeuten, dass ein Element fehlt oder ein Wert nicht stimmt; das Element im
Verlauf bearbeiten und erneut prüfen.

## 10. STEP exportieren

Werkzeug **STEP exportieren …** (`Strg+E`). _Körper 1_ wählen, _AP214_ beibehalten und die
Datei speichern. Die Datei wird vor dem Ersetzen einer vorhandenen Datei neu eingelesen und mit
dem Modell verglichen. Die Statusleiste bestätigt Dateiname und Größe.

Mit `Strg+S` das Projekt speichern, um später weiterzuarbeiten. Die Projektdatei enthält Scan,
Bereiche, Ausrichtung und jeden Schritt des Verlaufs.
