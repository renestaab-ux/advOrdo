#!/bin/bash
# Übersetzt das Hilfsprogramm für Apple Intelligence (nur macOS 26 oder neuer, Apple Silicon).
# Voraussetzung einmalig: xcode-select --install
# Ergebnis: macos/apple-ki/build/advordo-apple-ki; der Kern findet es dort von selbst.
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(uname)" != "Darwin" ]; then
  echo "Apple Intelligence gibt es nur unter macOS." >&2
  exit 1
fi
mkdir -p build
xcrun swiftc -O -o build/advordo-apple-ki main.swift
echo "Fertig: $(pwd)/build/advordo-apple-ki"
echo '{"aktion":"status"}' | build/advordo-apple-ki
