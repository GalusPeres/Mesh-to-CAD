### Added

- Scans are imported from binary and ASCII STL, OBJ and PLY. The import panel shows the
  dimensions in the chosen unit, the triangle count, the scan noise and the proposed project
  tolerance; scans above 2,000,000 triangles are reduced during import.
- Every import repairs the scan (triangles without area, duplicates, inconsistent orientation,
  inside-out parts) and removes loose small parts.
- Preparation tools in _Vorbereiten_: _Reparieren_ with selectable steps, _Kleine Teile
  entfernen_, _Löcher füllen_, _Reduzieren_, _Glätten_ (display only), _Auswahl löschen_ (Entf)
  and _Scaninformationen_. Each shows what it would change before OK, marks the affected
  triangles in the viewport and can be undone. Fits and regions are carried over to the changed
  scan.
- Projects are saved as `.m2c` files (the previous file is kept as `.m2c.bak`) and opened again
  with the same document, view and stage. New, open, save and save as are in _Datei_ with
  Strg+N, Strg+O, Strg+S and Strg+Umschalt+S.
- The window title shows the project name and marks unsaved changes; closing, _Neues Projekt_
  and _Projekt öffnen_ ask before unsaved changes are lost.
- After a crash, the last state of the project is offered for restore at the next start.
- The recent files list keeps the last ten scans and projects.
