# advOrdo – Logo und Bildmarke

- `advordo-logo.png`: Logo mit Schriftzug (1264 × 1264 px, aus der gelieferten SVG-Datei, die nur ein eingebettetes Rasterbild enthält).
- `advordo-symbol-1024.png`: Bildmarke ohne Schriftzug, Quelle der App-Icons.

Die App-Icons in `app/src-tauri/icons/` stammen aus dieser Bildmarke (`icon.ico` für Windows, aus den PNG-Größen 16 bis 256 neu zusammengesetzt, `icon.icns` für macOS, PNG für Linux). Die Seitenleiste und das Fenstersymbol der Oberfläche nutzen `app/src/bilder/advordo-128.png`.

Farben der Bildmarke: Navy `#102C52`, Türkis `#138B88`.

Eine nachgezeichnete Vektorfassung gibt es noch nicht. Wer die Icons neu erzeugen will, nimmt am besten eine solche Vektorfassung oder die 1024er-PNG und `npx tauri icon`.
