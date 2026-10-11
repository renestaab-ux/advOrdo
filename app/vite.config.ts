import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Feste Ports, damit Tauri im Entwicklungsmodus den Dev-Server findet.
// src-tauri beobachtet Tauri selbst; unter Windows sperrt der Rust-Build dort Dateien (EBUSY).
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true, watch: { ignored: ["**/src-tauri/**"] } },
  envPrefix: ["VITE_", "TAURI_ENV_"],
  build: { target: "es2021", sourcemap: false },
});
