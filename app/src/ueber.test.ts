import { describe, expect, it } from "vitest";
import paket from "../package.json";
import tauriConf from "../src-tauri/tauri.conf.json";
import cargo from "../src-tauri/Cargo.toml?raw";
import pyproject from "../../core/pyproject.toml?raw";
import { BESTANDTEILE, QUELLEN } from "./Ueber";

/** „Über advOrdo“ nennt eine Version; Oberfläche, Fenster und Kern müssen dieselbe tragen. */
describe("Über advOrdo", () => {
  it("Versionen von Oberfläche, Tauri und Kern stimmen überein", () => {
    const toml = (text: string) => /^version\s*=\s*"([^"]+)"/m.exec(text)?.[1];
    expect(tauriConf.version).toBe(paket.version);
    expect(toml(cargo)).toBe(paket.version);
    expect(toml(pyproject)).toBe(paket.version);
  });

  it("die Lizenz der Pakete ist die EUPL-1.2", () => {
    expect(paket.license).toBe("EUPL-1.2");
    expect(cargo).toMatch(/^license\s*=\s*"EUPL-1\.2"/m);
    expect(pyproject).toMatch(/^license\s*=\s*"EUPL-1\.2"/m);
  });

  it("jede Quelle und jeder Bestandteil ist vollständig beschrieben", () => {
    for (const q of QUELLEN) expect([q.name, q.adresse, q.inhalt, q.hinweis].every((t) => t.trim().length > 0)).toBe(true);
    for (const b of BESTANDTEILE) expect([b.name, b.zweck, b.lizenz].every((t) => t.trim().length > 0)).toBe(true);
  });
});
