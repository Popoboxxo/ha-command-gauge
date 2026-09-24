# ha-command-gauge

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v1.2.0-beta.2 — `2026-09-13`
>
> **Längenempfehlung:** 200–500 Zeilen optimal. Über 500 Zeilen → Detailwissen in
> `docs/ARCHITECTURE.md`, `docs/API.md` o.ä. auslagern und manuell verlinken.
> Agent-spezifisches Wissen → `.claude/3-project/<rolle>-ext.md` (Extension).
>
> **CLAUDE.md Hierarchie (Claude Code lädt in dieser Reihenfolge):**
> 1. `~/.claude/CLAUDE.md` — global, alle Projekte (~50 Zeilen max, persönliche Präferenzen)
> 2. `<projekt>/CLAUDE.md` — diese Datei, projektspezifisch (von agent-meta verwaltet)
> 3. `<ordner>/CLAUDE.md` — optional in Unterordnern (z.B. `src/backend/CLAUDE.md`)

---

## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

---

## Projekt

**Name:** ha-command-gauge
**Präfix:** hcg
**Plattform:** Home Assistant Custom Integration (HACS)
**Beschreibung:** HACS Custom Integration für Home Assistant, die direkt gegen die CommandCode-API spricht und CommandCode-Nutzung, Credits, Limits und Abrechnung als Entities bereitstellt.

> Struktur: siehe Verzeichnisstruktur im Repo (`ls`/`find`); deklarativ: `.meta-config/project.yaml` → `variables.PROJECT_STRUCTURE`.

**Verzeichnisstruktur:**
```
custom_components/command_gauge/
  __init__.py       # Setup / Config-Entry-Registrierung
  config_flow.py    # API-Token-Konfiguration
  coordinator.py    # CommandCode-API-Client und DataUpdateCoordinator
  entity.py         # Basis-Entities und Option-Persistenz
  sensor.py         # Credit-, Fenster-, Summary- und Katalog-Sensoren
  binary_sensor.py  # Erreichbarkeit, Abo-Status und Limit-Warnungen
  number.py         # Live-Einstellungen
  switch.py         # Auto-Refresh-Schalter
  button.py         # Manueller Sofort-Refresh
  diagnostics.py    # Redigierter Diagnose-Export
  const.py          # Konstanten und defensives Parsing
  manifest.json
  strings.json
  translations/en.json
  translations/de.json
tests/

```

> Runtime & Abhängigkeiten: siehe Projekt-Manifest (`pyproject.toml` / `requirements.txt` / `package.json` / `manifest.json`).

**Entry-Point:** `custom_components/command_gauge/__init__.py — Integration-Setup`

**Besondere Patterns:**
- Ein DataUpdateCoordinator pro CommandCode-Konto
- CommandCode-Alpha-Endpunkte defensiv als voneinander unabhängige Datenquellen behandeln
- Pro Verbraucher mindestens ein verständlicher Teilzustand; niemals fehlende Daten als 0 ausgeben
- Modelle als dynamisches JSON-Attribut statt als Entity pro Modell

## Code-Konventionen

- Python 3.12+, Home-Assistant-Integrationskonventionen (async, DataUpdateCoordinator)
- snake_case für Module/Funktionen, PascalCase für Klassen
- Type Hints und defensive Parser für alpha/undokumentierte API-Felder
- Keine Secrets in Logs, State-Attributen, Exceptions oder Git

## Build & Development

```bash
# Build
(kein Build — reine Python-Integration)

# Tests
pytest

# Dev-Stack starten
(kein Dev-Stack — Tests gegen HA-Stubs und optionale QS-Instanz)

# Nach Änderungen neu laden

```

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- Konto-, Credit-, Fenster- und Summary-Daten
- Config Flow / Setup / Diagnostics
- Polling, Fehlertoleranz und Sicherheit


## Agenten-Konfiguration

<!-- agent-meta:managed-begin -->
<!-- Dieser Block wird von sync.py bei jedem sync automatisch aktualisiert. -->
<!-- Manuelle Änderungen hier werden überschrieben. -->

> **AI ROUTING:** Claude -> CLAUDE.md | Opencode -> AGENTS.md

Generiert von agent-meta v1.2.0-beta.2 — `2026-09-13`
DoD-Preset: **standard** | REQ-Traceability: false | Tests: true | Codebase-Overview: false | Security-Audit: false
> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.
<!-- agent-meta:managed-end -->
