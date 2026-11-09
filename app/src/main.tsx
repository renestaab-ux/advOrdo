import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { darstellungStarten } from "./darstellung";
import "./styles.css";

// Das Toolbox-Fenster lädt nur die Toolbox, nicht die ganze App.
const App = lazy(() => import("./App"));
const Toolbox = lazy(() => import("./Toolbox"));
const Arbeitsfenster = lazy(() => import("./Arbeitsfenster"));

// Zusätzliche Fenster laden dieselbe Oberfläche mit ?fenster=… (siehe src-tauri/src/fenster.rs).
const adresse = new URLSearchParams(window.location.search);
const fenster = adresse.get("fenster");
// Arbeitsfenster einer Akte: fenster=akte&akte=<id>.
const akteId = Number(adresse.get("akte"));

// Hell/Dunkel, Farbakzent und Schriftgröße vor dem ersten Zeichnen, damit nichts aufblitzt.
darstellungStarten();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Suspense fallback={null}>
      {fenster === "toolbox" ? (
        <Toolbox />
      ) : fenster === "akte" && Number.isInteger(akteId) && akteId > 0 ? (
        <Arbeitsfenster akteId={akteId} />
      ) : (
        <App />
      )}
    </Suspense>
  </React.StrictMode>,
);
