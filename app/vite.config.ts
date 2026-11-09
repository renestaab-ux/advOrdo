import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import paket from "./package.json" with { type: "json" };

// Feste Ports, damit Tauri im Entwicklungsmodus den Dev-Server findet.
// src-tauri beobachtet Tauri selbst; unter Windows sperrt der Rust-Build dort Dateien (EBUSY).
export default defineConfig({
  plugins: [react()],
  // Programmversion für „Über advOrdo“ in der Vorschau ohne Tauri; in der App liefert Tauri sie selbst.
  define: { __APP_VERSION__: JSON.stringify(paket.version) },
  clearScreen: false,
  server: { port: 1420, strictPort: true, watch: { ignored: ["**/src-tauri/**"] } },
  envPrefix: ["VITE_", "TAURI_ENV_"],
  build: { target: "es2021", sourcemap: false },
});
