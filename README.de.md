# Mesh-to-CAD

[English](README.md)

Mesh-to-CAD baut 3D-Scans (STL, OBJ, PLY) als bearbeitbare Volumenmodelle nach und exportiert sie
als STEP. Das Programm läuft unter Windows 10 und 11 (x64) und arbeitet ohne Internetverbindung.

**Stand:** frühe Entwicklung. Das Programm startet, importiert einen Scan, zeigt ihn in der
3D-Ansicht an und unterstützt Rückgängig. Die Modellierwerkzeuge entstehen gerade; eine
Veröffentlichung gibt es noch nicht.

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
`npm run check` führt alle Prüfungen und Tests aus; [CONTRIBUTING.md](CONTRIBUTING.md) nennt die
einzelnen Befehle.

## Aufbau

Das Programm besteht aus drei Prozessen: dem Electron-Hauptprozess (Fenster, Dateien,
Sicherheit), einem abgeschotteten Renderer (React-Oberfläche und three.js-Ansicht) und einem
Python-Rechenprozess, der [Open CASCADE](https://dev.opencascade.org/) über
[OCP](https://github.com/CadQuery/OCP) für die Volumenmodellierung sowie numpy und scipy für die
Netzverarbeitung und das Einpassen nutzt. Sie tauschen binäre Nachrichten über die Standardein-
und -ausgabe aus. Details stehen in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) und
[docs/DESIGN.md](docs/DESIGN.md).

## Dokumentation

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
