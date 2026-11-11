// Hilfsprogramm für advOrdo: das Sprachmodell von Apple Intelligence auf diesem Mac („On-Device“).
//
// Der Python-Kern startet das Programm je Anfrage, schreibt ein JSON-Objekt auf die Standardeingabe und liest ein
// JSON-Objekt von der Standardausgabe. Es öffnet keinen Port und baut keine Netzwerkverbindung auf. Verwendet wird
// ausschließlich SystemLanguageModel, das Modell auf dem Gerät; Private Cloud Compute wird nicht angesprochen.
//
// Anfragen:
//   {"aktion": "status"}
//   {"aktion": "chat", "system": "…", "nutzer": "…", "schema": {…} | null, "antwort_token": 1024}
// Antworten:
//   {"ok": true, "verfuegbar": true, "grund": null, "deutsch": true, "system": "macOS 26.1", "kontext": 4096}
//   {"ok": true, "text": "{…}"}
//   {"ok": false, "fehler": "kontext" | "schutz" | "sprache" | "nicht_bereit" | "json" | "schema" | "anfrage"
//                         | "nicht_verfuegbar" | "sonstiges", "meldung": "…"}
//
// Das Schema kommt als JSON-Schema-Ausschnitt (object, array, string mit enum, integer, number, boolean). Weil JSON
// keine Reihenfolge der Schlüssel kennt, nennt der Kern sie in "x-reihenfolge"; das Modell erzeugt die Felder in
// dieser Reihenfolge (etwa erst den Absatz, dann das Zitat).
//
// Übersetzen: ./bauen.sh (braucht macOS 26 und die Xcode-Befehlszeilenwerkzeuge).

import Foundation
import FoundationModels

func ausgeben(_ wert: [String: Any]) {
    let daten = (try? JSONSerialization.data(withJSONObject: wert, options: [])) ?? Data("{\"ok\":false}".utf8)
    FileHandle.standardOutput.write(daten)
    FileHandle.standardOutput.write(Data("\n".utf8))
}

func fehler(_ art: String, _ meldung: String) {
    ausgeben(["ok": false, "fehler": art, "meldung": meldung])
}

struct SchemaFehler: Error {
    let meldung: String
}

/// Baut aus dem JSON-Schema-Ausschnitt ein dynamisches Schema für die geführte Ausgabe.
func baue(_ s: [String: Any], name: String) throws -> DynamicGenerationSchema {
    let beschreibung = s["description"] as? String
    let typ = s["type"] as? String ?? (s["enum"] != nil ? "string" : "")
    switch typ {
    case "object":
        let eigenschaften = s["properties"] as? [String: Any] ?? [:]
        let pflicht = Set(s["required"] as? [String] ?? [])
        var reihenfolge = s["x-reihenfolge"] as? [String] ?? []
        for schluessel in eigenschaften.keys.sorted() where !reihenfolge.contains(schluessel) {
            reihenfolge.append(schluessel)
        }
        var felder: [DynamicGenerationSchema.Property] = []
        for schluessel in reihenfolge {
            guard let unter = eigenschaften[schluessel] as? [String: Any] else { continue }
            let feld = try baue(unter, name: "\(name)_\(schluessel)")
            felder.append(DynamicGenerationSchema.Property(
                name: schluessel, description: unter["description"] as? String, schema: feld,
                isOptional: !pflicht.contains(schluessel)))
        }
        return DynamicGenerationSchema(name: name, description: beschreibung, properties: felder)
    case "array":
        guard let eintrag = s["items"] as? [String: Any] else {
            throw SchemaFehler(meldung: "Liste ohne items bei \(name)")
        }
        return DynamicGenerationSchema(
            arrayOf: try baue(eintrag, name: "\(name)_eintrag"),
            minimumElements: s["minItems"] as? Int, maximumElements: s["maxItems"] as? Int)
    case "string":
        if let werte = s["enum"] as? [String] {
            return DynamicGenerationSchema(name: name, description: beschreibung, anyOf: werte)
        }
        return DynamicGenerationSchema(type: String.self)
    case "integer":
        return DynamicGenerationSchema(type: Int.self)
    case "number":
        return DynamicGenerationSchema(type: Double.self)
    case "boolean":
        return DynamicGenerationSchema(type: Bool.self)
    default:
        throw SchemaFehler(meldung: "Typ \(typ.isEmpty ? "(fehlt)" : typ) bei \(name) wird nicht unterstützt")
    }
}

/// Kontextgröße des Modells in Token, soweit macOS sie nennt (ab macOS 26.4).
func kontextGroesse(_ m: SystemLanguageModel) -> Int? {
    if #available(macOS 26.4, *) {
        return m.contextSize
    }
    return nil
}

func grund(_ verfuegbarkeit: SystemLanguageModel.Availability) -> String? {
    switch verfuegbarkeit {
    case .available:
        return nil
    case .unavailable(let ursache):
        switch ursache {
        case .deviceNotEligible: return "geraet"
        case .appleIntelligenceNotEnabled: return "nicht_eingeschaltet"
        case .modelNotReady: return "nicht_bereit"
        @unknown default: return "unbekannt"
        }
    @unknown default:
        return "unbekannt"
    }
}

let eingabe = FileHandle.standardInput.readDataToEndOfFile()
guard let anfrage = (try? JSONSerialization.jsonObject(with: eingabe)) as? [String: Any],
      let aktion = anfrage["aktion"] as? String else {
    fehler("anfrage", "Die Anfrage ist kein JSON-Objekt mit „aktion“.")
    exit(0)
}

// Inhaltsfilter so durchlässig, wie Apple es für die Arbeit mit vorhandenem Text erlaubt: Schriftsätze schildern oft
// Gewalt, Straftaten oder Krankheiten. Die Einstellung wirkt laut Apple nur auf Antworten als freier Text.
let modell = SystemLanguageModel(guardrails: .permissiveContentTransformations)

switch aktion {
case "status":
    let v = ProcessInfo.processInfo.operatingSystemVersion
    let g = grund(modell.availability)
    ausgeben([
        "ok": true,
        "verfuegbar": g == nil,
        "grund": g.map { $0 as Any } ?? NSNull(),
        "deutsch": modell.supportsLocale(Locale(identifier: "de_DE")),
        "system": "macOS \(v.majorVersion).\(v.minorVersion)",
        "kontext": kontextGroesse(modell).map { $0 as Any } ?? NSNull(),
    ])

case "chat":
    if let g = grund(modell.availability) {
        fehler("nicht_verfuegbar", g)
        exit(0)
    }
    let system = anfrage["system"] as? String ?? ""
    let nutzer = anfrage["nutzer"] as? String ?? ""
    let antwortToken = anfrage["antwort_token"] as? Int
    let optionen = GenerationOptions(sampling: .greedy, maximumResponseTokens: antwortToken)
    let sitzung = LanguageModelSession(model: modell, tools: [], instructions: Instructions { system })
    do {
        if let roh = anfrage["schema"] as? [String: Any] {
            let schema: GenerationSchema
            do {
                schema = try GenerationSchema(root: try baue(roh, name: "antwort"), dependencies: [])
            } catch let f as SchemaFehler {
                fehler("schema", f.meldung)
                exit(0)
            } catch {
                fehler("schema", String(describing: error))
                exit(0)
            }
            let antwort = try await sitzung.respond(to: nutzer, schema: schema, includeSchemaInPrompt: true,
                                                    options: optionen)
            ausgeben(["ok": true, "text": antwort.content.jsonString])
        } else {
            let antwort = try await sitzung.respond(to: nutzer, options: optionen)
            ausgeben(["ok": true, "text": antwort.content])
        }
    } catch let f as LanguageModelSession.GenerationError {
        switch f {
        case .exceededContextWindowSize: fehler("kontext", f.localizedDescription)
        case .guardrailViolation: fehler("schutz", f.localizedDescription)
        case .unsupportedLanguageOrLocale: fehler("sprache", f.localizedDescription)
        case .assetsUnavailable: fehler("nicht_bereit", f.localizedDescription)
        case .decodingFailure: fehler("json", f.localizedDescription)
        default: fehler("sonstiges", String(describing: f))
        }
    } catch {
        fehler("sonstiges", String(describing: error))
    }

default:
    fehler("anfrage", "Unbekannte Aktion: \(aktion)")
}
