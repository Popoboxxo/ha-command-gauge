# Paritäts-Konzept: command_gauge ↔ go_gauge

> **Abgelöst (2026-10-06):** Die Pflegedatei der Parität ist jetzt die
> Feature-Matrix im Standard-Repo (`external/ha-gauge-standard/matrix/parity.md`,
> Kanon v1.2). Dieses Dokument bleibt als historisches Konzept stehen; der
> operative Abgleich läuft über den Kanon-Checker
> (`external/ha-gauge-standard/scripts/check_canon.py`) und `docs/cross-repo-sync.md`.

Stand: 2026-10-04 (command_gauge 0.2.0, go_gauge 1.5.2)

## Ziel

`command_gauge` (CommandCode-API) und `go_gauge` (OpenCode-Go-API) sind
geschwister-Integrationen mit demselben Aufbau: ein DataUpdateCoordinator pro
Konto/Workspace, defensiv unabhängige Datenquellen, Fenster-Auswertung,
Katalog als dynamische JSON-Attribute statt Einzel-Entities. Beide sollen
**funktionsgleich** (gleiche Patterns, gleiche Entity-Sätze wo die API hergibt)
und **stilistisch gleich** bleiben, damit Änderungen an der einen Seite
vorhersehbar auf der anderen nachgezogen werden können.

## Verzeichnis-/Datei-Mapping (1:1)

| command_gauge | go_gauge |
|---|---|
| `__init__.py` | `__init__.py` |
| `config_flow.py` | `config_flow.py` |
| `coordinator.py` | `coordinator.py` |
| `entity.py` | `entity.py` |
| `sensor.py` | `sensor.py` |
| `binary_sensor.py` | `binary_sensor.py` |
| `number.py` | `number.py` |
| `switch.py` | `switch.py` |
| `button.py` | `button.py` |
| `diagnostics.py` | `diagnostics.py` |
| `const.py` | `const.py` |
| `scripts/check_json_consistency.py` | `scripts/check_json_consistency.py` |
| `scripts/check_version_sync.py` | `scripts/check_version_sync.py` |

## Feature-Matrix

### Entity-Plattformen

| Plattform | command_gauge | go_gauge | Status |
|---|---|---|---|
| sensor | ✅ | ✅ | identisch |
| binary_sensor | ✅ | ✅ | identisch |
| number | ✅ | ✅ | identisch |
| switch | ✅ | ✅ | identisch |
| button | ✅ | ✅ | identisch |

`PLATFORMS`-Liste und Dateinamen sind in beiden Repos gleich
(eiserne Regel „Plattform == Dateiname").

### Sensoren

| Sensor (pro Fenster) | command_gauge | go_gauge | Status |
|---|---|---|---|
| Usage (%) | ✅ | ✅ | identisch |
| Reset (timestamp) | ✅ | ✅ | identisch |
| Forecast (%) | ✅ | ✅ | identisch |
| Pace (Ampel) | ✅ inkl. Icon/Attribute (seit 0.2.0) | ✅ inkl. Icon/Attribute | identisch |
| Remaining (%) | ✅ | ✅ | identisch |
| Time to reset (h) | ✅ | ✅ | identisch |
| Burn rate (%/h) | ✅ | ✅ | identisch |

| Konto-/Katalog-Sensor | command_gauge | go_gauge | Status |
|---|---|---|---|
| Credits (monthly/purchased/free/remaining) | ✅ | — (kein Credit-Modell) | domain-spezifisch |
| Total cost / Requests / Tokens | ✅ | — | domain-spezifisch |
| Plan / Subscription | ✅ | ✅ (je Workspace) | ähnlich |
| Model-Katalog (1 Sensor, JSON-Attribute) | ✅ (`models`) | ✅ (`model_catalog` + Ranking) | ⚠️ siehe Abweichungen |
| Live-Modelle / Günstigstes / Free | — | ✅ | ⚠️ API-blockiert |

### Binary Sensoren

| Sensor | command_gauge | go_gauge | Status |
|---|---|---|---|
| Account/API erreichbar | ✅ (`account_reachable`, immer verfügbar) | ✅ (`api_reachable`, Catalog-Owner) | ähnlich |
| Subscription aktiv | ✅ | ✅ | identisch |
| Credits unter Schwelle | ✅ | — | domain-spezifisch |
| Fenster-Limit überschritten | ✅ (`window_exceeded`) | ✅ (`rate_limited`) | ähnlich |
| Fensteranzahl | 2 (5h, week) | 3 (5h, week, month) | ⚠️ API-abhängig |

### Number / Switch / Button / Optionen

| Entity | command_gauge | go_gauge | Status |
|---|---|---|---|
| Usage-Intervall (Number) | ✅ (5–1440 min) | ✅ (1–1440 min) | ⚠️ Min. bewusst domain-begründet |
| Models-Intervall (Number) | ✅ (60–1440 min) | ✅ (1–1440 min) | ⚠️ dto. |
| Warnschwelle / Pace-Rot (Number) | ✅ (1–100 / 1–1000) | ✅ (1–100 / 1–300) | ⚠️ dto. |
| Auto-Update-Schalter | ✅ (usage, models) | ✅ | identisch |
| Refresh-Button | ✅ (erzwingt beide Zyklen) | ✅ | identisch |
| Options-Flow (Schwellen, Intervalle, Auto) | ✅ | ✅ | identisch |

### Coordinator-Verhalten

| Verhalten | command_gauge | go_gauge | Status |
|---|---|---|---|
| Ein Coordinator pro Config-Entry | ✅ (pro CommandCode-Konto) | ✅ (pro Workspace) | identisch |
| Getrennte, abschaltbare Auto-Zyklen (usage/models) | ✅ | ✅ | identisch |
| `persist_options` ohne Entry-Reload (`_skip_reload`) | ✅ | ✅ | identisch |
| Defensive, unabhängige Datenquellen | ✅ (5 Sektionen + `section_status`) | ✅ (Workspaces + Status) | identisch |
| Offline-pending Setup (ohne erste Validierung) | ✅ | — | command_gauge-führend |
| Catalog-Owner (nur erste Instanz legt Katalog an) | — | ✅ | ⚠️ siehe Abweichungen |

## Abweichungen und wie man sie schließt

1. **`suggested_object_id`-Pinning fehlt in beiden Repos.** Die eiserne Regel
   aus AGENTS.md (Objekt-IDs auf Englisch pinnen, Referenz-Implementierung in
   `ha-health-o-mat`) ist weder in command_gauge noch in go_gauge 1.5.2
   umgesetzt. Beweis für die Relevanz: die 0.1.1-Live-Instanz von
   command_gauge hat deutsch Erstregistrierte Entity-IDs
   (`account_erreichbar`, siehe CHANGELOG 0.1.1). **Schließung:** gemeinsam in
   beiden Repos umsetzen (HA-Internals `platform_data`/`_name_internal`, Test-
   Stubs erweitern); für command_gauge zusätzlich eine Entity-Registry-
   Migration der vorhandenen deutschen Slugs erwägen (Analogie go_gauge v6/v7,
   `er.async_migrate_entries`). Nicht release-blockend, aber vor breiter
   Verbreitung sinnvoll.
2. **Katalog-Sensoren (live_count, cheapest, free, ranking_by_cost).**
   go_gauge berechnet sie aus Pricing-Daten der OpenCode-API. Die CommandCode
   `/provider/v1/models`-Antwort liefert nur `id`/`name`/`context_length` —
   ohne API-Erweiterung nicht umsetzbar. **Schließung:** nur wenn die
   CommandCode-API Pricing liefert; dann `build_models_block` erweitern und
   die go_gauge-Sensoren spiegeln.
3. **Catalog-Owner-Pattern.** go_gauge legt den workspace-unabhängigen
   Katalog nur über die erste Instanz an. Bei command_gauge ist jeder Entry
   ein eigenes CommandCode-Konto mit eigenem Katalog — ein Duplikat-Problem
   existiert nicht. **Schließung:** entfällt.
4. **Fenster „month"**. go_gauge wertet 5h/week/month aus; die
   CommandCode-API liefert nur 5h/week (`WINDOW_API_KEYS`). **Schließung:**
   falls die API ein Monatsfenster ergänzt, `WINDOW_LABELS`/`WINDOW_SECONDS`/
   `WINDOW_API_KEYS` in `const.py` erweitern — der Sensor-Satz pro Fenster ist
   bereits dynamisch über `WINDOW_LABELS`.
5. **Testtiefe.** go_gauge hat u. a. Forecast-Pace-, Runtime-Settings- und
   Entity-Migrations-Tests; command_gauge hat Client/Coordinator/Section- und
   Wiring-Tests (53). **Schließung:** bei jedem neuen command_gauge-Feature
   denselben Test-Typ wie im go_gauge-Gegenstück anlegen.
6. **CI-/Tooling-Differenzen.** command_gauge 0.2.0 hat mit
   `release-version-sync` einen Job, den go_gauge noch nicht hat —
   **nachziehen** im nächsten go_gauge-Release. go_gauge hat mypy (Config +
   CI-Job) und `icons/` — bei Bedarf nachziehen.

## Verfahren für zukünftige Änderungen

1. **Spiegelungs-Pflicht:** Jede Pattern- oder Feature-Änderung an einer
   Integration wird im selben Arbeitsgang am Schwester-Repo geprüft und —
   soweit die API hergibt — gespiegelt. Betroffene Dateien über das
   1:1-Mapping oben identifizieren.
2. **API-Differenzen dokumentieren, nicht verbiegen:** Wenn eine Abweichung
   durch die jeweilige API begründet ist (Pricing, Workspaces, Credits,
   Fenster), wird sie in dieser Matrix begründet und mit
   „Schließungsbedingung" versehen — nicht durch synthetische
   Nachbildungen „geschlossen".
3. **Gemeinsame Konventionen (beide AGENTS.md, identisch):** Conventional
   Commits auf Englisch, Branch-Guard (`feat/`, `fix/`, `chore/`), SemVer
   (MAJOR bei Entity-Breaking), Release-Dreiklang (Commit → Tag → echtes
   GitHub-Release, Tag ↔ `manifest.version`), eiserne HACS-Regeln
   (`unique_id` nie ändern, keine `_attr_name`-Literale, `strings.json` =
   englischer Master, `iot_class` nur im manifest).
4. **Naming parallel halten:** `translation_key`s, Options-Konstanten und
   Coordinator-Attributnamen (`warn_percent`, `pace_red_percent`,
   `usage_minutes`, `models_minutes`, `auto_usage`, `auto_models`) sind
   bewusst identisch und bleiben es.
5. **Release-Kopplung:** Paritäts-relevante Änderungen möglichst im selben
   Release-Zyklus beider Repos ausliefern, damit HACS-User beider
   Integrationen denselben Stand vorfinden.
6. **Werkzeuge synchron halten:** `scripts/check_json_consistency.py` und
   `scripts/check_version_sync.py` sind ports-identisch; Änderungen daran
   immer in beiden Repos gleichzeitig vornehmen.

## Verwandte Dokumente

- `docs/cross-repo-sync.md` — der operative Teil: Paar-Change-Checkliste,
  Auslöser/Rollen, Versions-Disziplin, Prozess für API-blockierte
  Differenzen, koordinierte TODOs und Session-Praxis (Containment).
