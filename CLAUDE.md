# Projektregeln

Gemeinsame Regeln für die Arbeit an diesem Repository, auf allen Systemen (Zorin OS, Windows 11, macOS).

- Sprache: Oberfläche, Fachbegriffe und Dokumentation auf Deutsch. Bezeichner im Code dürfen deutsche Fachbegriffe tragen (Norm, Absatz, Fassung).
- Eine Codebasis für Windows, macOS und Linux. Plattformspezifischer Code nur, wo technisch zwingend, und dann hinter einem Adapter. Keine an ein Betriebssystem gebundene Haupttechnologie.
- Datenschutz: Der Kern öffnet keinen Netzwerkport. Dokumentinhalte verlassen das Gerät nur im ausdrücklich gewählten Modus „Externer Anbieter“. Ohne Rückfrage darf die App nur öffentliche Rechtsquellen aus dem Netz laden.
- Beleg vor Behauptung: Jede Aussage muss auf eine Fundstelle zurückführbar sein (Dokument, Seite/Rn. oder Norm mit Fassung). Keine erfundenen Fundstellen; fehlende Belege ausdrücklich benennen.
- Rechtsquellen werden unverändert archiviert (SHA-256) und versioniert; bestehende Fassungen werden nie überschrieben.
- Echte Mandatsdaten gehören nie ins Repository, auch nicht als Testdaten. Testakten nur anonymisiert.
- Vor jedem Commit: `pytest` und `ruff check` in `core/`, `npm run build` und `npm test` in `app/`, `cargo test` in `app/src-tauri/`. CI prüft alles auf allen drei Systemen.
