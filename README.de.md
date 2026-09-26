# Mesh-to-CAD

[English](README.md)

Mesh-to-CAD baut 3D-Scans (STL, OBJ, PLY) als bearbeitbare Volumenmodelle nach und exportiert sie
als STEP. Das Programm läuft unter Windows 10 und 11 (x64) und arbeitet ohne Internetverbindung.

**Stand:** Version 0.1.0, für den unten beschriebenen Umfang vollständig und durchgehend
getestet; noch nicht als Release veröffentlicht. Gemessene Genauigkeit und Geschwindigkeit stehen in
[docs/RESULTS.md](docs/RESULTS.md) (englisch).

![Auto-Flächen auf dem Scan des Stanford-Armadillo](docs/images/02-auto-surface.png)

## Was funktioniert

- **Organische Scans → STEP:** _Auto-Flächen_ macht aus einem geschlossenen Scan einen gültigen
  Volumenkörper aus B-Spline-Flächen. Stanford-Armadillo (346.000 Dreiecke): 3.000 Flächen in
  21 s, Abweichung RMS 0,29 mm bei 229 mm Bauteilgröße; mit einer durchgeschnittenen
  Zylinderbohrung liest sich die STEP-Datei als gültiger Körper zurück, alle Freiformflächen sind
  B-Splines.
- **Technische Teile → STEP:** Ebenen, Zylinder, Kegel, Kugeln und Tori einpassen, auf einem
  Schnitt durch den Scan skizzieren, extrudieren, drehen, kombinieren, verrunden. Bei einem
  verrauschten Flansch-Scan (σ 0,03 mm) liegen gemessene Radien und Höhen weniger als 0,001 mm
  neben den Konstruktionswerten und rasten exakt auf ihnen ein; das Volumen des nachgebauten
  Körpers weicht um weniger als 0,0001 % ab.
- Alles in der Liste unten ist umgesetzt; die 3D-Ansicht zeigt einen Scan mit 2 Millionen
  Dreiecken nach 0,8 s und dreht ihn mit etwa 160 Bildern pro Sekunde.

| Importierter Scan                                      | Exportierter Körper                            |
| ------------------------------------------------------ | ---------------------------------------------- |
| ![Importierter Scan](docs/images/01-scan-imported.png) | ![STEP-Export](docs/images/03-step-export.png) |

## Umfang von Version 0.1

Version 0.1 richtet sich an prismatische und rotationssymmetrische Teile wie Halter, Flansche,
Adapter, Deckel, Wellen und Drehknöpfe, gescannt mit einem 3D-Scanner für Endanwender.

- Scans im Format STL, OBJ und PLY importieren; reparieren, reduzieren, kleine Löcher füllen,
  kleine Teile und einzelne Dreiecke entfernen.
- Den Scan an einem Bauteil-Koordinatensystem ausrichten, automatisch oder an eingepassten Flächen.
- Bereiche mit Pinsel, Flächenauswahl, Lasso oder Rechteck auswählen oder den Scan automatisch
  segmentieren.
- Ebenen, Zylinder, Kegel, Kugeln und Tori einpassen. Die Güte wird gegen eine Projekttoleranz
  angezeigt, und aus der Messung werden Konstruktionswerte vorgeschlagen (zum Beispiel
  „Radius 8,000 mm, gemessen 7,987 ± 0,012“).
- Auf Schnitten durch den Scan skizzieren, mit automatisch eingepassten Linien, Bögen und Kreisen.
- Körper durch Extrusion, Drehung, Grundkörper, Teilen, Kombinieren, Verrundung und Fase aufbauen,
  in einem bearbeitbaren Verlauf.
- Das Modell vermessen und in einer Abweichungsdarstellung mit dem Scan vergleichen.
- STEP (AP214 oder AP242, durch Zurücklesen geprüft) und STL exportieren.
- Benutzeroberfläche auf Deutsch und Englisch.

Der vollständige Umfang, einschließlich dessen, was Version 0.1 nicht enthält, steht in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#1-product-scope) (englisch).

## Voraussetzungen

- Windows 10 oder 11, 64 Bit.
- Eine Grafikkarte mit WebGL-2-Unterstützung (jede integrierte Grafik der letzten zehn Jahre).
- 8 GB Arbeitsspeicher; 16 GB empfohlen für Scans mit mehr als einer Million Dreiecken.

## Installieren

Das Installationsprogramm entsteht mit `npm run dist` (siehe unten) unter
`release\Mesh-to-CAD-0.1.0-Setup.exe`. Nach der Installation startet man _Mesh-to-CAD_ über das
Startmenü. Ohne Installation läuft `release\win-unpacked\Mesh-to-CAD.exe`.

## Aus dem Quellcode bauen

Benötigt werden [Node.js](https://nodejs.org/) 24, [Python](https://www.python.org/) 3.12
(64 Bit) und Git. Ein C++-Compiler ist nicht nötig.

```powershell
git clone https://github.com/GalusPeres/Mesh-to-CAD.git
cd Mesh-to-CAD
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r kernel\requirements-dev.txt
npm ci
npm run dev
```

`npm run dev` startet das Programm und lädt die Benutzeroberfläche bei Änderungen neu.
`npm run check` führt alle Prüfungen und Tests aus, `npm run build; npx playwright test` die
End-to-End-Tests, und `npm run dist` baut das Installationsprogramm;
[CONTRIBUTING.md](CONTRIBUTING.md) nennt die einzelnen Befehle.
`node scripts/py.mjs scripts/verify_scenarios.py` wiederholt die Messungen aus
[docs/RESULTS.md](docs/RESULTS.md).

## Aufbau

Das Programm besteht aus drei Prozessen: dem Electron-Hauptprozess (Fenster, Dateien,
Sicherheit), einem abgeschotteten Renderer (React-Oberfläche und three.js-Ansicht) und einem
Python-Rechenprozess, der [Open CASCADE](https://dev.opencascade.org/) über
[OCP](https://github.com/CadQuery/OCP) für die Volumenmodellierung sowie numpy und scipy für die
Netzverarbeitung und das Einpassen nutzt. Sie tauschen binäre Nachrichten über die Standardein-
und -ausgabe aus. Details stehen in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) und
[docs/DESIGN.md](docs/DESIGN.md).

## Dokumentation

- [Messergebnisse](docs/RESULTS.md) (englisch)
- [Architektur](docs/ARCHITECTURE.md) (englisch)
- [Designsystem](docs/DESIGN.md) (englisch)
- [Mitwirken](CONTRIBUTING.md) (englisch)
- [Sicherheitsrichtlinie](SECURITY.md) (englisch)
- [Änderungsprotokoll](CHANGELOG.md)

## Lizenz

Mesh-to-CAD steht unter der [MIT-Lizenz](LICENSE). Verwendete Komponenten Dritter und ihre
Lizenzen sind in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) aufgeführt.

## Danksagung

Mesh-to-CAD baut auf Open CASCADE Technology, den vom CadQuery-Projekt gepflegten OCP-Bindings,
trimesh, numpy, scipy, three.js, three-mesh-bvh, React und Electron auf.
