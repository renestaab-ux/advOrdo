import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { darstellungStarten } from "./darstellung";
import "./styles.css";

// Das Toolbox-Fenster lädt nur die Toolbox, nicht die ganze App.
const App = lazy(() => import("./App"));
const Toolbox = lazy(() => import("./Toolbox"));

// Zusätzliche Fenster laden dieselbe Oberfläche mit ?fenster=… (siehe src-tauri/src/fenster.rs).
const fenster = new URLSearchParams(window.location.search).get("fenster");

// Hell/Dunkel, Farbakzent und Schriftgröße vor dem ersten Zeichnen, damit nichts aufblitzt.
darstellungStarten();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Suspense fallback={null}>{fenster === "toolbox" ? <Toolbox /> : <App />}</Suspense>
  </React.StrictMode>,
);
