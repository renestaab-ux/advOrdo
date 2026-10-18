import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Toolbox from "./Toolbox";
import "./styles.css";

// Zusätzliche Fenster laden dieselbe Oberfläche mit ?fenster=… (siehe src-tauri/src/fenster.rs).
const fenster = new URLSearchParams(window.location.search).get("fenster");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {fenster === "toolbox" ? <Toolbox /> : <App />}
  </React.StrictMode>,
);
