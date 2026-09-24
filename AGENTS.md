# ha-command-gauge

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


<!-- agent-meta:managed-begin -->
> **ROUTING:**

 Opencode->AGENTS.md |
 Gemini->AGENTS.md
> **ENTRY:** `orchestrator`-Agent (für alle Dev-Tasks).
`agent-meta v1.2.0-beta.2` | DoD: `standard` | REQ-Trace: `false`



## Regeln

# A2A Anti-Re-Delegation Gates

## Enforced Gates (aktiv prüfen — HARD REJECT)

1. **No Self-Handoff / No Re-Delegation:** Ein `payload`, der mit "Du bist..." beginnt, ist ein Re-Delegations-/Spec-Dump-Versuch → HARD REJECT.
2. **Orchestrator-Singleton:** NUR `main_chat` darf den `orchestrator` spawnen. Worker → `orchestrator` → HARD REJECT (siehe `singleton-orchestrator-architecture.md`).
3. **Execution-Trace-Isolation:** Worker-Output muss strukturiert sein (STATUS, RESULT, ARTIFACTS). Keine rohen Logs propagieren.

## Degradierte Checks (Doku-Pflicht, kein Gate — Issue #346)

Diese Checks sind dokumentierte Konventionen, keine erzwungenen Gates. Die
eigene Modell-Prüfung war Ritual ohne Gate-Wirkung — Plattform-Limits decken
den praktischen Fehlerfall ab:

| Check | Status | Begründung |
|---|---|---|
| `delegation_depth ≤ 10` | dokumentiert | Die Plattform (z.B. Claude Code) erzwingt Tiefenlimits ohnehin; eigene Prüfung ist redundant. Referenz: `docs/concepts/a2a-handoff-protocol.md` |
| `payload.t ≤ 300 Zeichen` | dokumentiert | Empfehlung für prägnante Task-Zeilen; der Re-Delegation-Check (Punkt 1) deckt den eigentlichen Fehlerfall (Spec-Dump) ab |
| `max_depth` via project.yaml (`orchestrator.delegation.max_depth`) | dokumentiert | Toter Konfigurationsraum bei einem 2-Ebenen-Repo; der enforced-Pfad wurde aus `validate_envelope()` entfernt, der Doku-Verweis bleibt |

## Per-Task-Tier: `payload.tier_override` (optional — Issue #346)

Neues optionales Envelope-Feld: `payload.tier_override: <tier>` übersteuert die
Rolle→Tier-Auflösung (`role-defaults.yaml` → `model`) nur für genau diesen Dispatch.

**Guardrails (Referenz-Implementierung: `resolve_tier_override()` in `scripts/lib/delegation_syntax.py`):**

1. **Preset-Bounds:** Der Tier-Name muss im aktiven tier-preset existieren (`config/tier-presets.yaml` — globales `tiers:` plus `providers.<provider>.tiers` wenn Provider-Kontext vorliegt). Unbekannter Tier oder Tier außerhalb des Presets → Override wird verworfen, Fallback auf Rollen-Default.
2. **Kein Downgrade sicherheitskritischer Rollen:** Rollen aus `tier-override-policy.security-critical-roles` (`config/role-defaults.yaml`; Default: `security-auditor`, `code-reviewer`) können per Override nur gleich- oder höhergestuft werden.
3. **Audit-Log-Pflicht:** Jeder Override-Versuch — angenommen ODER abgelehnt — wird im Delegations-Tracker/Checkpoint protokolliert: `tier_override=<tier> (applied|rejected: <reason>)`.

## Runtime-Enforcement-Tier: `permission`

Ob der `# CRITICAL GATE` („MAIN CHAT darf nicht selbst editieren") auf diesem
Provider per Runtime-Gate (`hook`/`plugin`), nur partiell über den
Permission-Layer (`permission`, ohne Delegations-Provenienz) oder rein
prompt-basiert (`advisory`) durchgesetzt wird, nennt das Tier
`permission`. Die konkreten Grenzen dieses Schutzes stehen unter
„Bekannte Grenzen".

## Bekannte Grenzen

- **Singleton-Orchestrator (Punkt 2) wird nur über eine Selbstdeklaration der Agenten-Identität gestützt** (`#agent-meta:agent=<name>` in `.claude/hooks/orchestrator-guard.sh`), die im Hook-Quelltext selbst als "soft, self-reported convention, not a security boundary" dokumentiert ist. Jeder Agent kann sich technisch als privilegiert deklarieren. **Das ist eine bewusste Design-Grenze, kein behebbarer Bug:** Claude Code liefert seit Kurzem zwar ein `agent_id`-Feld im PreToolUse-Payload (harness-gesetzt, nicht selbst-deklariert — seit Issue #683 genutzt, um Write/Edit/Bash für JEDEN dispatchten Subagenten von der Strict-Mode-Main-Chat-Blockade freizustellen), aber das sagt nur "irgendein Subagent", nicht "welche Rolle". Für die ROLLEN-Identität (git vs. orchestrator, für den Git-Mutation-Gate) liefert kein Provider ein echtes Feld — der Hook kann die Sentinel-Behauptung also weiterhin nicht verifizieren. Der Guard ist ein Konventions-Schutz gegen Versehen, kein Schutz gegen einen Agenten, der die Regel bewusst umgeht. Wer eine harte Grenze braucht, muss Git-Mutationen außerhalb des Agenten-Systems absichern (Branch-Protection, Pre-Receive-Hooks, Review-Pflicht) — zerstörerische Operationen (`push --force`, `reset --hard`, `clean -fd`, `branch -D`) bleiben deshalb ausdrücklich zustimmungspflichtig durch den Nutzer.
- **`resolve_tier_override()` ist dormant by design** — es gibt keinen Interception-Punkt im Runtime-Dispatch (siehe `validate_envelope()`-Docstring in `scripts/lib/delegation_syntax.py`). Die Guardrails sind prompt-basiert durchgesetzt (Orchestrator-Template, Tier-Selection-Sektion); die Python-Funktion ist die testbare Referenz-Implementierung.
- **`subagent_permissions` (optional) ist auf ALLEN Providern prompt-basiert plus Sync-Time-Validierung** — es gibt keinen Runtime-Dispatch-Gate. Die `strict`/`warn`-Anweisung oben wird nur gerendert, wenn der Modus aktiv ist; ein Modell kann sie ignorieren (identische, akzeptierte Grenze wie bei `orchestrator.mode: strict`). Bei `off` wird nichts gerendert.
- **Große Ergebnisse gehören in Dateien, nicht in den Return-Channel.** Der synchrone Tool-Result-Kanal hat ein undokumentiertes Größenlimit; überlange Antworten können ohne Fehlersignal beschnitten zurückkommen (agent-meta #514). Read-only-Rollen ohne `Write` (`Plan`, `Explore`, `code-reviewer`) sind davon strukturell betroffen. Daher: Artefakte ab ~1000 Zeilen (Pläne, Konzepte, Reviews) immer von einer schreibfähigen Rolle in eine Datei schreiben lassen und nur den Pfad zurückgeben. Empfangene Ergebnisse auf Vollständigkeit prüfen (fehlender Kopf/erste Abschnitte = Truncation), nicht blind weiterverarbeiten.



# Branch-Guard

Verwende Feature-Branches (`feat/`, `fix/`, `chore/`). Keine Code-Änderungen direkt auf `main` oder `master`.

## Guard-Terminologie: Convention Boundary vs. Security Boundary

Guards im System (Orchestrator-Guard, DoD-Push-Check, etc.) werden inkonsistent als
"Konventions-Tool" und als "security boundary" bezeichnet — beide Aussagen sind korrekt,
aber gegen unterschiedliche Bedrohungsmodelle:

- **Convention boundary**: fail-closed gegen AKZIDENTIELLEN Missbrauch (Tippfehler,
  vergessene Bestätigungen, naive Automatisierung). Nicht darauf ausgelegt, einen
  gezielten Bypass-Versuch zu widerstehen (siehe Lücken unten, z.B. #592).
- **Security boundary**: fail-closed gegen einen DELIBERATEN Umgehungsversuch.

Diese Definition ist die zentrale Referenz — Hook-Header und andere Doku sollen sie
verlinken (`.claude/rules/branch-guard.md#guard-terminologie-convention-boundary-vs-security-boundary`)
statt sie ad hoc zu wiederholen.

`orchestrator-guard.sh` ist primär eine **convention boundary** (siehe Lücken unten),
mit einzelnen **security-boundary**-Eigenschaften für spezifische Fälle (z.B. das
Destructive-Gate aus #516, das auch bei gültigem `git`-Sentinel blockt). `dod-push-check.sh`
ist als **security boundary** gegen fehlendes/kaputtes `python3` fail-closed (#595).

## Bekannte Grenzen

Die technische Durchsetzung (`orchestrator-guard.sh`) erkennt Git-Mutationen über eine tokenisierte Analyse des Bash-Befehls (gemeinsamer Tokenizer für Destructive- und Mutation-Gate, Issue #551), kein vollständiger Shell-Parser. Bekannte Lücken:

1. `eval "git commit ..."` wird nicht erkannt.
2. Direkte Schreibzugriffe auf `.git/` werden nicht geprüft.
3. Andere Git-Tools (`hub`, `gh repo ...`) sind nicht erfasst.
4. Command-Substitution und Indirektion (`$(...)`, Backticks, `xargs`, `eval`) können eine Git-Mutation am Tokenizer vorbeischleusen, weil der Hook den Befehl weder ausführt noch die Shell vollständig parst (Issue #592). Ein echter Shell-Interpreter wäre unverhältnismäßig für ein Konventions-Tool.

Bewusster Trade-off, kein Bug (siehe Kommentar-Header in `.claude/hooks/orchestrator-guard.sh`) — nur relevant für Nutzer, die sich vollständig auf den Schutz statt auf die Konvention verlassen.



# Commit-Konventionen

Verwende Conventional Commits (feat, fix, chore).
Beschreibungssprache: `Englisch`
Max 72 Zeichen in erster Zeile. Imperativ.
Format: `<type>: <beschreibung>` (Bsp: `feat: ...`)



# Definition of Done (DoD)

Pflicht: Code komplett, Konventionen & Conv. Commits eingehalten, keine Regressions.
Tests: Test vorhanden & grün



# GitHub Issue Lifecycle

Issues referenzieren und am Ende mit passendem Keyword (`Fixes #123`, `Closes #123`) im PR oder Commit schließen. Kommentiere das Issue nach Fertigstellung.



# Sprachregeln

| Kontext | Sprache |
|---|---|
| User-Kommunikation | **Deutsch** |
| User-Input | **Deutsch** |
| Externe Doku | **Englisch** |
| Interne Doku | **Deutsch** |
| Code/Commits | **Englisch** |



# Lifecycle-Tasks

Beim Start prüfen: existiert `.gemini/pending-tasks.md bzw. .opencode/pending-tasks.md bzw. .codex/pending-tasks.md bzw. .zcode/pending-tasks.md bzw. .kimi-code/pending-tasks.md`?
Falls ja und enthält `- [ ]`: User fragen ob delegiert werden soll.
Nach Erledigung: löschen. Datei nicht committen.



# MCP Hard Prohibitions

> Kurzfassung der harten Tool-Verbote aktiver MCP-Server. Vollständige Tool-Listen und
> Hinweise: pro Provider in `.gemini/skills bzw. .opencode/skills bzw. .agents/skills bzw. .zcode/skills bzw. .kimi-code/skills` — jeweils `mcp-<server>/SKILL.md` (`use-lazy-rules.md`).

- (keine aktiven MCP-Server mit gesperrten Tools)



# No Worktree Isolation

**Anti-Pattern:** Niemals das Argument `isolation: "worktree"` beim Spawnen von Subagenten verwenden.
**Grund:** Agenten schreiben dann ihren Output in den internen Ordner `.claude/worktrees/agent-<id>/` anstatt in das eigentliche Projektverzeichnis. Das führt zu fehlgeleiteten Dateien und Datenverlust in der eigentlichen Codebase.

Alle Agenten müssen direkt im Projektverzeichnis arbeiten (Isolation deaktivieren oder weglassen). Der `.claude/` Ordner (sowie `.gemini/`, `.continue/`, `.mammouth/` etc.) ist strikt als Infrastruktur-Ordner zu betrachten und darf nicht für Arbeitskopien missbraucht werden.



# Repo-Containment („Gefängnis-Modus")

Repo-Containment ist AKTIV: Schreibzugriffe sind auf die Projekt-Wurzel beschränkt; einziger sanktionierter Ausnahmebereich ist `.tmp/`.
Durchsetzung: PreToolUse-Hook = **Convention boundary** (keine Security Boundary, nur gegen akzidentellen Missbrauch; Definition: `.claude/rules/branch-guard.md#guard-terminologie-convention-boundary-vs-security-boundary`). Grenzen/Details: `docs/concepts/repo-containment-prison-mode.md`.



# SE-Kaskade: ADR-Standard

Verbindlicher MADR-Minimal-Standard für Architecture Decision Records in der
SE-Kaskade (Issue #339 B1). Normativ nur bei aktiver SE-Kaskade.




# SE-Kaskade: Artefakt-Taxonomie

Verbindliche Taxonomie, Trennregel und Output-Location-Regeln für alle SE-Artefakte
(Issue #339 B3/B4, Issue #334). Normativ nur bei aktiver SE-Kaskade.




# SE-Kaskade: Review-Lifecycle

Verbindlicher Review-Lifecycle mit Protokoll-Pflicht und RVW-Finding-IDs für die
SE-Kaskade (Issue #339 B5). Normativ nur bei aktiver SE-Kaskade.




# Security Paved Roads

Security wird als vorgeprüfte Paved-Road-Blöcke geliefert, nicht als DIY-Aufgabe:
**invisible, consistent, embedded, non-optional** (Netflix Paved Roads / Golden Path).
Ein Block ist ausgereift, sicherheitsgeprüft und wird identisch überall verwendet —
niemand implementiert Security-Logik selbst neu.

## Block-Katalog

| Block | Abdeckt | Eigentümer-Agent |
|-------|---------|------------------|
| `auth-flow` | Authentifizierung (Login, Session, Token) | `security-auditor` |
| `dependency-check` | SBOM + CVE-Scan der Abhängigkeiten | `dependency-auditor` |
| `input-validation` | Eingabevalidierung (Schema, Sanitizing) | `security-auditor` |
| `rate-limiting` | Rate-Limiting / Throttling | `devops-engineer` |
| `cors-config` | CORS-Konfiguration | `security-auditor` |
| `secret-scanning` | Secret-Scan (Leaks in Diffs, Commits, Logs) | `security-auditor` |

## Enforcement

- **Vor jedem Commit:** Secret-Scan über den Block `secret-scanning` ausführen.
- **Vor jedem Deploy:** `dependency-check` (SBOM + CVE) ausführen.
- **Für neue Features:** den `auth-flow`-Block nutzen statt Auth selbst zu bauen.

DIY-Security ist eine Anti-Pattern: jede Variante erzeugt unbekannte Lücken.
Abweichungen vom Block-Katalog werden als Review-Befund von `security-auditor`
gemeldet, nicht als Eigenbau gerechtfertigt.



# Session-Abschluss

Delegate Session-Zusammenfassung an `documenter` am Ende großer Features, um CODEBASE_OVERVIEW.md aktuell zu halten.



# Submodule-Schutzkonzept

Regeln für den Umgang mit allen Git-Submodulen (`.agent-meta/`, `external/*/`, und alle weiteren in `.gitmodules`):

- **Keine direkten Änderungen in Submodul-Verzeichnissen:** Dateien in `.agent-meta/`, `external/*/` und allen anderen Submodul-Pfaden dürfen in Konsumenten-Repositories niemals direkt editiert oder committet werden. Submodule sind separate Repositories mit eigenem Lifecycle (Build, Push, Deploy, Version-Tags). Änderungen MÜSSEN im Submodul-Repo selbst durchgeführt, committet und gepusht werden — danach aktualisiert das Parent-Repo die Pinned-Commit-Referenz.
- **Keine Mutation von `.gitmodules` / Git Staging:** `.gitmodules` darf nicht automatisch modifiziert werden und Submodule dürfen nicht automatisch via `git add` gestaged werden.
- **Kein Source-Code-Scaffolding in Konsumenten-Projekten:** In Konsumenten-Projekten wird kein Anwendungscode generiert/gerüstet; verwaltet werden ausschließlich `.meta-config/project.yaml` und die Managed Blocks.
- **Framework-Änderungen nur im agent-meta Repo:** Änderungen am agent-meta Framework müssen auf Feature-Branches im agent-meta Repository selbst durchgeführt werden.



# Threat Model — die 4 Fragen

Vor jedem öffentlichen Release die 4 Fragen beantworten (Igor Andriushchenko,
CISO Lovable):

1. **Was baust du?** — Datenspeicherung, Auth, Autorisierung, woher kommen die User?
2. **Was könnte schiefgehen?** — Worst-Case-Szenarien (Leak, Bypass, Datenverlust).
3. **Was tust du dagegen?** — konkrete Gegenmaßnahme pro Risiko.
4. **Was sind die Konsequenzen?** — Business-Impact, Datenverlust, Reputation.

## Anwendung

- `concept-reviewer` prüft die 4 Fragen in Design-Docs (Threat-Model-Checkliste).
- `orchestrator` stellt die 4 Fragen vor Feature-Releases.
- **Interne Apps:** vereinfacht — 1–2 Fragen reichen.
- **Customer-facing Apps:** vollständig — alle 4 Fragen plus dokumentiertes Threat Model.



# Lazy-Loaded Rules

> Nicht immer geladen — bei Bedarf per `Read` öffnen: `.gemini/skills bzw. .opencode/skills bzw. .agents/skills bzw. .zcode/skills bzw. .kimi-code/skills/<skill>/SKILL.md` (jeweils).

| Skill | Wann |
|---|---|
| sync-interface | sync.py, Templates/Rules ändern |
| admin-ui | Admin-Server/UI betreiben (Lifecycle, Token, Ports) |
| architecture | Templates/Overrides/Placeholder ändern |
| conventions | Vor Commits in agents/, config/, scripts/lib |
| submodule-protection | .agent-meta/, external/, .gitmodules |
| a2a-delegation-gates | A2A-Delegation an Subagenten |
| issue-lifecycle | GitHub-Issue |
| lifecycle-tasks | Session-Start, pending-tasks.md vorhanden |
| session-conclusion | Feature-Abschluss |
| provider-agnostic | agents/1-generic editieren |
| mcp-reqogniloom | ReqogniLoom-MCP-Tools |
| mcp-honcho | Honcho-MCP-Memory-Tools |
| mcp-playwright | Playwright-MCP-Browser-Tools |
| mcp-viz-logger | viz-logger Event-Logging |
| tool-graphify | Architektur-/Datei-Fragen mit graphify |

Harte MCP-Tool-Verbote: siehe `mcp-guardrails.md` (always-on).



# CRITICAL GATE (runtime-partially enforced)
MAIN CHAT darf nicht selbst editieren. ALLES -> `orchestrator`.
Provider-native Permissions block Main-Chat-Writes; Delegations-Provenienz ist
NICHT erzwungen (Prompt + Permission-Layer).

## Git Delegation
Git Mutationen (commit, push, add etc) -> `git` Agent. Read-only (status, log) im Main Chat ok.

Native Extensions (Skills/Hooks) erlaubt, ignorieren nicht Branch-Guard/DoD.
Skill-getriebene Sub-Agent-Loops (z.B. generische Harness-Skills wie `subagent-driven-development`) sind KEINE dritte Ausnahme von der Orchestrator-Pflicht: ein Skill darf einen bereits vom `orchestrator` gestarteten Loop ausführen, aber niemals selbst zum Einstiegspunkt für einen neuen Dev-Task werden. Einzige Ausnahmen bleiben User-Override.

Anti-Recursion: Worker dürfen nicht an `orchestrator` zurück delegieren.



# HACS Integration Development

Verbindlicher Ablauf für die Entwicklung von Home-Assistant-Custom-Components, die über
**HACS** (Home Assistant Community Store) distribuiert werden. Der `hacs-developer` trägt
die kompakten Always-on-Anker; dieser Skill ist die vollständige Referenz (Workflow,
eiserne Regeln mit Begründung/Fehlerklasse, Meta-Datei-Skelett, Test-Trick, Debugging).

## Live-Referenzen dieses Projekts

| Bezug | Wert |
|---|---|
| Integrations-Repo (dieses Projekt) | `{{platform.hacs.integration_repo_url}}` |
| Referenz-Repo (z.B. home-assistant/core) | `{{platform.hacs.reference_repo_url}}` |
| Projekt-Skills (Entwicklung + Review-Gegenstück) | `{{platform.hacs.project_skills}}` |
| Dev-Instanz (Home Assistant) | `{{platform.hacs.dev_instance_url}}` |
| Components-Pfad im Integrations-Repo | `{{platform.hacs.custom_components_path}}` |

**Wenn die Werte oben leer sind oder noch unaufgelöste `platform.hacs.*`-Platzhalter
enthalten:** die Werte fehlen bzw. sind in `.claude/platform-config.yaml` des Projekts
nicht gesetzt (sync.py warnt dazu in `sync.log`). Fallback: Repo-URLs via `git remote -v`
prüfen, Dev-Instanz und Skills beim User erfragen — und die Werte in
`.claude/platform-config.yaml` nachtragen, damit der nächste Sync sie einarbeitet.

## 7-Schritte-Workflow (Reihenfolge zwingend)

1. **Ist-Analyse live per API** — Recherche gegen die Live-Referenzen (Integrations-Repo,
   Referenz-Repo, Projekt-Skills), inkl. Live-Abfrage der Dev-Instanz. Nie aus
   Erinnerung antizipieren: bestehende Entities, Versionen und Entity-Generationen
   zuerst am echten System prüfen.
2. **Konzept** — Name/Domain nach der Domain-Regel (snake_case, **keine Bindestriche**;
   `iot_class` gehört nur ins `manifest.json`, nie ins `hacs.json`), Entity-Schema
   (`unique_id` + `device_info` ab Entity #1), Migrationspfad falls Bestands-Entries
   existieren.
3. **Logik in HA-freie Module** — Reine Logik (Aggregation, Fenster, Serialisierung)
   ohne `homeassistant`-Import. Das ist die Grundlage der Unit-Tests (Test-Trick unten).
4. **Bauen** — Implementierung im Repo-Layout (siehe `hacs-developer`); Meta-Dateien
   und CI von Tag 1 (Skelett unten).
5. **Tests grün** — HA-freie Unit-Tests komplett grün; danach **Pre-Release-E2E** auf
   der Dev-Instanz (Integration manuell installiert/kopiert: laden, Setup-Flow,
   Entities prüfen).
6. **Release-Dreiklang** — Commit → Tag → echtes GitHub Release mit Changelog.
   Tag ↔ `manifest.version` synchron. HACS verteilt nur echte Releases.
   Tag-Format: Stable `v1.2.3`, Beta `v1.3.0b0` als Pre-Release — Details im
   Abschnitt Release-Naming-Best-Practice unten.
7. **Erst dann: Dev-Test & Alt-Cleanup** — HACS kann nur freigegebene Versionen
   ausliefern: der **HACS-Update-Test** (Update von der Vorgängerversion auf der
   Dev-Instanz) und der **Alt-Entity-Cleanup** (verwaiste Alt-Entities entfernen —
   Device-Ansicht prüfen, nicht nur Entitäten-Liste; entfernen statt umbiegen,
   `unique_id` wird nie geändert) laufen **nach** dem Release-Dreiklang, nie davor.

## Eiserne Regeln (Begründung + Fehlerklasse)

### Releases

| Regel | Begründung | Fehlerklasse bei Verstoß |
|---|---|---|
| Tag allein reicht nicht — Release-Dreiklang (Commit → Tag → echtes GitHub Release mit Changelog) | HACS verteilt ausschließlich echte GitHub Releases, keine bloßen Tags | HACS zeigt kein Update; User bleibt auf Alt-Version |
| Tag ↔ `manifest.version` synchron (z.B. `v1.2.3` ↔ `"version": "1.2.3"`) | Release-Asset und Integrations-Selbstauskunft müssen übereinstimmen | Installierte Version meldet Alt-Stand; Update-Erkennung kaputt |
| `manifest.VERSION` nur mit registriertem `async_migrate_entry`-Handler erhöhen | HA ruft beim Entry-Update den Migrator für die neue VERSION auf | `Migration handler not found` beim User-Update |

### Entities

| Regel | Begründung | Fehlerklasse bei Verstoß |
|---|---|---|
| `unique_id` + `device_info` ab Entity #1 | Nachträglich ergänzen erzeugt bei HA komplett neue Entity-IDs — der Alt-Bestand bleibt verwaist | Entity-Generation-Chaos; verwaiste Duplikat-Entities |
| `unique_id` nie ändern | HA koppelt Automatisierungen, Dashboards und History an die unique_id | Beim Update wird jede betroffene Entity neu angelegt; User-Setup bricht |
| `suggested_object_id` auf den englischen Namen pinnen (`has_entity_name` + `translation_key` für den lokalisierten Anzeigenamen) | HA >= 2026.9 erzeugt object_ids für Sprachen in `NATIVE_ENTITY_IDS` (u.a. Deutsch) aus der lokalisierten Übersetzung statt aus dem Englischen — ohne Pinning wechselt object_id/entity_id mit der Systemsprache | entity_id ändert sich/verwaist bei Sprachwechsel — gleiche Schadensklasse wie die `unique_id`-Regel, nur über einen anderen Mechanismus (`unique_id` != object_id) |
| Plattform == Dateiname (`PLATFORMS`-Eintrag `<name>` braucht `<name>.py`) | HA lädt Plattform-Module per Dateinamen | `ModuleNotFoundError: custom_components.<domain>.<platform>` |

### Architektur

| Regel | Begründung | Fehlerklasse bei Verstoß |
|---|---|---|
| Entry-Registry in `hass.data[DOMAIN][entry_id]` | Services und Diagnostics greifen zentral darauf zu | Services finden keine Daten / liefern leere Antworten |
| Dynamische Anzahl (beliebig viele Config-Entries, keine Singleton-Annahme) | HA erlaubt mehrere Entries derselben Integration | Zweiter Entry überschreibt den ersten; Setup bricht bei Reload |
| On-read statt Reset-Job (Fenster/Aggregate beim Lesen berechnen) | Reset-Services/Automations sind Zombies nach Restart und verlieren Zustand | Datenverlust bei Restart; tote Reset-Automations im System |

### Flows

| Regel | Begründung | Fehlerklasse bei Verstoß |
|---|---|---|
| Nie blockierend validieren (kein synchrones I/O im Config-Flow) | Blocking Calls frieren den HA-Event-Loop ein | UI friert ein / Event-Loop blocked |
| Korrigierbares in Options-Flow (nicht `entry.data`) | Einstellungen müssen ohne Neuaufsetzen änderbar sein | User muss Integration löschen + neu anlegen |
| Strukturelle Daten explizit in `entry.data` schreiben | Implizite Abhängigkeiten brechen Reproduzierbarkeit und Migration | Setup-Reproduzierbarkeit kaputt; Migration verliert Daten |

### Datenschutz

| Regel | Begründung | Fehlerklasse bei Verstoß |
|---|---|---|
| Diagnostics ohne Geheimnisse/Gesundheitsdaten | Der Diagnostics-Download geht ins öffentliche GitHub Issue | Secret-Leak im Issue-Tracker |
| Exporte nie nach `/config/www` | `/www` ist über den HA-Webserver öffentlich erreichbar | Datenleck über HTTP |
| Tokens zentral speichern (Storage/Entry-Data, nicht verteilt) | Verteilte Tokens landen in Entity-Attributen und Logs | Token im State-Objekt/Log sichtbar |

## Sprache, Namen & Identität

Ergänzt die eiserne Regel `suggested_object_id` (Tabelle Entities oben) um Referenz-Code
und die Etikette für eine geteilte Dev-Instanz.

**Object-ID-Pinning (Referenz-Implementierung):** `Popoboxxo/ha-health-o-mat`,
`custom_components/health_o_mat/entity.py`, Basisklasse `HealthOMatEntity`:

```python
@property
def suggested_object_id(self) -> str | None:
    """Objekt-IDs (Entity-ID-Suffixe) immer aus dem ENGLISCHEN Namen.

    HA >= 2026.9 erzeugt für Sprachen in NATIVE_ENTITY_IDS (u. a. Deutsch)
    Objekt-IDs in der Systemsprache — die IDs würden mit der Sprache
    wechseln (z. B. `melder_sehr_schlecht`). Wir pinnen die Suffixe auf
    Englisch: stabil, lesbar, sprachunabhängig. Der Anzeigename bleibt
    davon unberührt (folgt weiterhin der Systemsprache).
    """
    platform_data = self.platform_data
    if (
        platform_data is not None
        and type.__getattribute__(self.__class__, "name")
        is type.__getattribute__(Entity, "name")
    ):
        name = self._name_internal(
            self._object_id_device_class_name,
            getattr(platform_data, "default_language_platform_translations", None) or {},
        )
        if name is not UNDEFINED:
            return name
    return super().suggested_object_id
```

Kombiniert mit `has_entity_name = True` + `_attr_translation_key`: der **Anzeigename**
bleibt lokalisiert (folgt der Systemsprache), das **object_id/entity_id** ist auf
Englisch gepinnt — stabil und sprachunabhängig.

**Namenslokalisierung (Referenz-Implementierung):** Der Anzeigename kommt ausschließlich
aus den Übersetzungen — der Code trägt **kein** Namens-Literal:

```python
class HealthOMatPowerSensor(HealthOMatEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "power"
    # VERBOTEN (nicht lokalisierbar, bricht den Sprachwechsel):
    # _attr_name = "Leistung"
    # name = "Leistung"  # Property-Override mit Literal
```

| Regel | Begründung | Fehlerklasse |
|---|---|---|
| Jedes hartcodierte `_attr_name`/`name`-Literal ist **absolut verboten** — stattdessen `_attr_has_entity_name = True` + `_attr_translation_key`. Keine Ausnahme für `has_entity_name = False`. | Nur so zieht HA den Anzeigenamen aus `strings.json`/`translations` und respektiert den Sprachwechsel; ein Literal friert eine Sprache dauerhaft ein | `friendly_name` wechselt nicht mit der Systemsprache — identische Schadensklasse wie das Object-ID-Pinning (`unique_id` != object_id) |

**Master/Ableitung:** `strings.json` ist der englische Master; `translations/{de,en}.json`
sind abgeleitet (siehe Meta-Dateien-Skelett unten) — der Master trägt die Identität,
Übersetzungen tragen nur den zur Laufzeit angezeigten `friendly_name`.

**Erstregistrierungs-Regel:** Ohne das Pinning oben (oder auf HA < 2026.9) bestimmt die
zum Zeitpunkt der **Erstregistrierung** aktive Systemsprache das object_id dauerhaft —
Entities in der beabsichtigten Sprache erstregistrieren, eine spätere Umbenennung ist
ein Breaking Change (vgl. `unique_id` nie ändern, Tabelle Entities oben).

**Rename = Breaking Change:** Jede Änderung, die die `entity_id`-Erzeugung verschiebt
(`entity_id`, `original_name`, `translation_key`, Object-ID-Pinning), ist ein Breaking
Change → **MAJOR** + **💥-Eintrag mit Migrationshinweis** (Entity-Registry-Migration
unten, `manifest.VERSION`-Bump; Release-Naming-Best-Practice). Für den Umgang mit dem
Alt-Bestand gilt der Verweis auf den **Post-Release-Orphan-Cleanup** in Workflow-Schritt
7: verwaiste Alt-Entities werden erst **nach** dem Release entfernt, nie durch Ändern der
`unique_id`.

**Etikette auf einer geteilten Dev-Instanz** (mehrere Integrationen/Domains auf derselben
Home-Assistant-Instanz):

| Aspekt | Regel |
|---|---|
| Sync (Neustart, ~10–30s) | Pro-Domain sicher — die Registry der anderen Domains bleibt erhalten |
| Reset | Destruktiv für **alle** Domains auf der Instanz — vorher koordinieren, nicht ungefragt ausführen |
| `unique_id` | Akkumuliert dauerhaft in der geteilten Registry über alle Domains hinweg — nie ändern (Tabelle Entities oben) |
| Systemsprache wechseln | Instanzweiter Blast-Radius: rendert `friendly_name`s **aller** Domains neu und riskiert Erstregistrierungen laufender Arbeiten anderer Domains — vorher koordinieren |
| Tokens/State | Nie committen oder zwischen Domains kopieren |

### Entity-Registry-Migration bei Umbenennung

Ein Rename ändert **nie** die `unique_id` (eiserne Regel Entities oben). Geändert werden
ausschließlich `entity_id` und `original_name` — über den HA-Entity-Registry-Helper
`er.async_migrate_entries`, aufgerufen **innerhalb** des registrierten
`async_migrate_entry`-Handlers, zusammen mit einem `manifest.VERSION`-Bump
(Breaking → MAJOR, siehe Release-Naming-Best-Practice unten). Das ist **nicht** das
`entry.data → entry.options`-Rezept weiter oben: dort wandern Entry-Daten, hier werden
Entity-Registry-Einträge umbenannt.

```python
# custom_components/<domain>/__init__.py
from homeassistant.helpers import entity_registry as er

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 -> v2: Entity umbenennen, unique_id bleibt stabil."""
    if entry.version < 2:
        def _rename(reg_entry: er.RegistryEntry) -> dict[str, str] | None:
            if reg_entry.unique_id == "health_o_mat_power_old":
                return {
                    "new_entity_id": "sensor.health_o_mat_power",
                    "original_name": "Power",
                }
            return None

        er.async_migrate_entries(hass, entry.entry_id, _rename)
        hass.config_entries.async_update_entry(entry, version=2)
    return True
```

`manifest.json`: `"version": "2.0.0"` (Breaking), GitHub-Release mit 💥-Entry und
Migrationshinweis. Verwaiste Alt-Entities werden erst im **Post-Release-Cleanup**
(Workflow-Schritt 7) entfernt — nie durch Ändern der `unique_id`.

## Release-Naming-Best-Practice

Verbindliches Naming für Tags, `manifest.version` und GitHub-Releases — ergänzt die
eisernen Regeln Releases um Format- und Lifecycle-Details. HACS leitet die Version aus
dem Tag des letzten echten GitHub Releases ab und vergleicht Versionen mit
AwesomeVersion (PEP-440), nicht per String-Parsing — Formatfehler führen zu
`Invalid version` bzw. kaputter Update-Erkennung.

| Regel | Begründung | Fehlerklasse bei Verstoß |
|---|---|---|
| Stable-Tags als `vMAJOR.MINOR.PATCH`; der `v`-Prefix gehört **nur** in den Tag | `v1.2.3` ist Tag-Konvention, keine Semantic Version | `v` in `manifest.version` → `Invalid version` (hassfest/HACS-Validation) |
| `manifest.version` = bare SemVer **ohne** `v`, exakt dem Tag-Suffix entsprechend (`v1.2.3` ↔ `"version": "1.2.3"`) | Release-Asset und Integrations-Selbstauskunft müssen zeichenidentisch sein; Versionsvergleiche laufen über AwesomeVersion (PEP-440) | Abweichung → installierte Version meldet Alt-Stand; Sortier-/Update-Erkennung kaputt |
| Beta-/Pre-Release-Tags als `vX.Y.Zb<N>` (z.B. `v1.3.0b0`) und das GitHub-Release als **pre-release** flaggen; `manifest.version` entspricht exakt dem Tag-Suffix (`v1.3.0b0` ↔ `"version": "1.3.0b0"`) | PEP-440-Beta-Suffix `b<N>` sortiert korrekt vor dem Stable-Release; HACS 2.0 liefert Pre-Releases nur über die `switch.<repo>_pre_release`-Entity (default OFF) aus | Beta ohne pre-release-Flag → alle User bekommen die Beta via Update-Check |
| Promotion beta→stable = neuer Release (`v1.3.0`), nie den Tag mutieren; Tags/Releases sind immutable — nie verschieben, löschen, wiederverwenden | HACS cacht Versionen; verschobene/gelöschte Tags bleiben in bestehenden Installationen referenziert | Tag-Reset/Mutation → User bleiben auf Alt-Stand; Update-Check findet die Version nicht mehr |
| Release-Notes-Mindeststruktur: Summary + ✨ New features + 💥 Breaking changes (je mit Migration-Hinweis; Breaking-Notes sind bei MAJOR Pflicht wegen der Migrator-Regel) + Full-Changelog-Link; optional zusätzlich `CHANGELOG.md` | HACS zeigt die letzten Releases in der Update-Auswahl; User entscheiden anhand der Notes über das Update | Fehlende Breaking-Notes → User aktualisieren ohne Migrationshinweis; Setup bricht beim Update |
| SemVer-Disziplin: MAJOR = Breaking, MINOR = Feature, PATCH = Fix; `unique_id`-/Entity-Änderungen sind **immer** breaking → MAJOR; `v0.x` nicht ohne Hinweis als „stabil" deklarieren | Entity-Änderungen erzeugen bei HA neue Entity-IDs (eiserne Regel Entities) — für Bestands-User zwingend Breaking | Entity-Änderung als MINOR/PATCH → User verlieren stillschweigend Entities und Automatisierungen |

Quellen:

- <https://hacs.xyz/docs/publish/start> — „If the repository uses GitHub releases, the tag name from the latest release is used to set the remote version. Just publishing tags is not enough, you need to publish releases."
- <https://hacs.xyz/docs/use/entities/switch> — HACS 2.0 Pre-Release-Mechanik (GitHub pre-release-Flag → `switch.<repo>_pre_release`, default OFF); Beispiel-Tags `v1.0.0`, `v2.0.0b0`
- <https://developers.home-assistant.io/docs/versioning> — HA nutzt PEP-440-Suffixe (`b<N>` für Betas); Versionsvergleich via AwesomeVersion, kein String-Parsing
- <https://semver.org/#is-v123-a-semantic-version> — FAQ: `v1.2.3` ist keine Semantic Version (der `v`-Prefix ist reine Tag-Konvention)
- <https://github.com/hacs/integration/releases> — Vorbild für die Release-Notes-Struktur (What's Changed / ✨ New features / 💥 Breaking changes / Full Changelog)

## Meta-Dateien-Skelett (händisch anlegen — kein Generator)

Die Skelette sind Vorlagen zum Abtippen und ans Projekt anzupassen. Es gibt keinen
Generator — Dateien nicht blind übernehmen.

### `hacs.json` (Repo-Root)

```json
{
  "name": "Human readable integration name",
  "render_readme": true,
  "homeassistant": "2024.1.0"
}
```

`name` ist Pflicht. `homeassistant` = unterstützte HA-Minimalversion.

### `custom_components/<domain>/manifest.json`

```json
{
  "domain": "snake_case_domain",
  "name": "Human readable name",
  "version": "0.1.0",
  "codeowners": ["@your-github-user"],
  "config_flow": true,
  "documentation": "https://github.com/your-org/your-integration",
  "issue_tracker": "https://github.com/your-org/your-integration/issues",
  "iot_class": "cloud_polling",
  "requirements": []
}
```

`iot_class` gehört **nur hierhin**, nie ins `hacs.json`. `version` muss beim Release
dem Git-Tag entsprechen (eiserne Regel Releases).

### Migrations-Rezept: `entry.data` → `entry.options`

Konkretisiert die eiserne Regel „`manifest.VERSION` nur mit registriertem
`async_migrate_entry`-Handler erhöhen" (Tabelle Releases oben) für den häufigsten Fall:
strukturelle Daten bleiben in `entry.data`, editierbare Daten wandern verlustfrei nach
`entry.options`. Worked example: `Popoboxxo/ha-health-o-mat`, `config_flow.py`.

| Version | `entry.data` | `entry.options` |
|---|---|---|
| v1 | alles (inkl. editierbarer Werte) | leer |
| v2 | nur strukturelle Daten (z.B. Host, Domain-Identität) | editierbare Werte (z.B. Schwellwerte, Intervalle) |

```python
# custom_components/<domain>/__init__.py
STRUCTURAL_KEYS = {"host"}  # Beispiel: an das eigene Schema anpassen

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old entry.data layout to the current version."""
    if entry.version == 1:
        new_data = {k: v for k, v in entry.data.items() if k in STRUCTURAL_KEYS}
        new_options = {
            **entry.options,
            **{k: v for k, v in entry.data.items() if k not in STRUCTURAL_KEYS},
        }
        hass.config_entries.async_update_entry(
            entry, data=new_data, options=new_options, version=2
        )
    return True
```

### `custom_components/<domain>/strings.json` (Master) + `translations/{de,en}.json`

Master `strings.json` ist **englisch** (hassfest-Konvention) — der Master trägt die
Identität, allein `translations/*.json` tragen die lokalisierten Anzeigewerte:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Set up connection",
        "data": { "host": "Host or IP address" }
      }
    },
    "error": { "cannot_connect": "Connection failed" }
  },
  "options": {
    "step": {
      "init": { "data": { "scan_interval": "Update interval (seconds)" } }
    }
  },
  "entity": {
    "sensor": {
      "power": { "name": "Power" }
    }
  }
}
```

Abgeleitet `translations/de.json` (nur Anzeige-Werte; die Identität bleibt im Master).
Der `entity`-Key muss exakt zum `_attr_translation_key` der Entity passen:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Verbindung einrichten",
        "data": { "host": "Host oder IP-Adresse" }
      }
    },
    "error": { "cannot_connect": "Verbindung fehlgeschlagen" }
  },
  "entity": {
    "sensor": { "power": { "name": "Leistung" } }
  }
}
```

Master ist `strings.json` (englisch); `translations/de.json` und `translations/en.json`
sind abgeleitet und bei jeder Änderung mitzupflegen (hassfest prüft die Konsistenz).
`entity.<platform>.<translation_key>.name` trägt den lokalisierten Anzeigenamen
(z.B. `entity.sensor.power.name` für `_attr_translation_key = "power"`); die
`entity_id` bleibt davon unberührt.

### `.github/workflows/validate.yml`

```yaml
name: Validate

on:
  push:
    branches: [main]
  pull_request:
  release:
    types: [published]

jobs:
  validate-hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: HACS validation
        uses: hacs/action@main
        with:
          category: integration

  validate-hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: hassfest validation
        uses: home-assistant/actions/hassfest@master
```

CI von Tag 1 (eiserne Regel: `hacs/action` + `hassfest`).

## Test-Trick: pytest ohne Home-Assistant-Installation

Reine Logik-Module importieren kein `homeassistant` (Workflow-Schritt 3). Der
Integrations-Code selbst schon — für seine Tests wird HA via Fake-Package in
`sys.modules` geladen, bevor die Integration importiert wird:

```python
# tests/conftest.py
"""Fake-Home-Assistant-Package: pytest läuft ohne echte HA-Installation."""
import sys
from unittest.mock import MagicMock

# Nur greifen, wenn homeassistant wirklich fehlt (echte Installation -> echter Import)
try:
    import homeassistant  # noqa: F401
except ImportError:
    _FAKE_MODULES = [
        "homeassistant",
        "homeassistant.core",
        "homeassistant.config_entries",
        "homeassistant.const",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.storage",
        "homeassistant.helpers.service",
        "homeassistant.helpers.config_validation",
        "homeassistant.util",
        "homeassistant.util.dt",
    ]
    for _mod in _FAKE_MODULES:
        sys.modules.setdefault(_mod, MagicMock())
```

Wichtig:

- **Jedes in der Integration importierte `homeassistant.*`-Sub-Modul** muss in der
  Liste stehen — ein einzelner Fake für `homeassistant` allein genügt nicht, weil
  `from homeassistant.helpers.entity import Entity` das Sub-Modul als eigenes Modul
  im `sys.modules` erwartet. Liste pflegen, wenn neue Imports dazukommen.
- `voluptuous` ist ein pip-Paket ohne HA-Abhängigkeit → echt installieren
  (z.B. in `tests/requirements.txt`), **nicht** faken.
- Die Tests mocken anschließend gezielt `hass`, `coordinator`, `store`; auf der
  Mock-Struktur kann die HA-freie Logik (Fenster, Serialisierung) echte Assertions
  bekommen statt nur Smoke-Tests.

## Debugging-Checkliste: „Es geht nicht"

In dieser Reihenfolge durchgehen:

1. **Alte Entity-Generation?** Device-Ansicht prüfen (nicht nur Entitäten-Liste) —
   verwaiste Alt-Entities sind Post-Release-Alt-Cleanup (Workflow-Schritt 7).
2. **`ModuleNotFoundError: custom_components.<domain>.<platform>`** → Plattform-Datei
   fehlt oder Plattform-Name ≠ Dateiname (eiserne Regel Entities).
3. **`Migration handler not found`** → `manifest.VERSION` ohne registrierten
   Migrator erhöht (eiserne Regel Releases).
4. **HACS zeigt kein Update?** → Echtes GitHub-Release statt nur Tag vorhanden?
   Tag ↔ `manifest.version` synchron? (eiserne Regel Releases).
5. **Setup bricht sofort ab?** → Syntax-/Import-Fehler in EINER Plattform-Datei
   killt die ganze Integration (alle Plattformen teilen den `__init__`-Import).
6. **Services finden nichts?** → `hass.data[DOMAIN][entry_id]`-Registry gefüllt?
   (eiserne Regel Architektur).
7. **Unit-Tests grün, aber auf der Instanz falsch?** → Reihenfolge respektiert?
   Logik HA-frei testen; E2E vor Release manuell, HACS-Update-Test erst nach dem
   Release-Dreiklang (Workflow-Schritte 5–7).







## Agent Directory
> ⚠️ **ACHTUNG:** Agenten (Prompts) liegen in `.gemini/agents bzw. .opencode/agents bzw. .codex/agents bzw. .zcode/agents bzw. .kimi-code/agents`.

| Agent | Core Capabilities |
|-------|-------------------|

| `accessibility-specialist` | WCAG 2.1/2.2 Compliance-Audit, ARIA-Checks, Keyboard-Navigation |

| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback |

| `agent-meta-scout` | Claude-Ökosystem scouten: neue Skills, Rollen, Rules |

| `ai-security-guardian` | KI-spezifische Sicherheitsrisiken: halluzinierte Deps, fabrizierte IAM, unsichere Defaults |

| `api-specialist` | OpenAPI/Contract-First API Design, Schnittstellen-Spezifikationen |

| `app-lifecycle-governor` | App-Lifecycle-Governance: Ownership, SLA, Data-Classification |

| `backend-reviewer` | Backend-Domain-Review: API-Contracts, Silent Failures, Concurrency |

| `bug-feature-analyzer` | Issue-Triage: Eingehende Bug-Meldungen, Feature-Requests analysieren, k |

| `claude-expert` | Absoluter Analyse-Experte für die Plattform Claude Code: Funktionsweise, Konf |

| `code-reviewer` | Clean Code Gatekeeper: Blast-Radius-Analyse, SOLID/DRY Prüfung, Code-Qualität |

| `concept-architect` | Systemdesign für komplexe Änderungen: Komponenten, Schnittstellen, Trade-offs |

| `concept-reviewer` | Konzept-Critic: reviewt Design-Docs, Konzepte auf Vollständigkeit, Logik |

| `concept-specifier` | Technische Spezifikationen aus Anforderungen, Codebase-Kontext — implementiert nicht |

| `continue-expert` | Absoluter Analyse-Experte für die Plattform Continue: Funktionsweise, Konfigu |

| `copilot-expert` | Absoluter Analyse-Experte für die Plattform GitHub Copilot: Funktionsweise, K |

| `copyeditor` | Lektorat: Stil, Satzbau, Wortwiederholungen |

| `data-engineer` | ETL/ELT-Pipelines, Schema-Migration (Datenebene), Data-Quality-Checks |

| `database-engineer` | Relationales Schema-Design, Datenbank-Migrationen, Query-Optimierung |

| `database-reviewer` | Datenbank-Domain-Review: Migration-Safety, N+1, Injection-Vektoren |

| `dependency-auditor` | Supply-Chain-Hygiene: SBOM-Analyse, Lizenz-Kompatibilität, Version-Drift und |

| `design-system-architect` | Design-System-Schema → echte Token-Artefakte, Farbharmonie, Variant-Contracts |

| `developer` | Feature-Implementierung, Bugfixes |

| `devops-engineer` | CI/CD, Infrastructure as Code, Kubernetes |

| `docker` | Dev-Stack verwalten, Test-Stack starten, Binary-Management |

| `documenter` | CODEBASE_OVERVIEW, ARCHITECTURE, README |

| `e2e-tester` | E2E-Tests, visuelle Regression, Accessibility-Audits via Playwright |

| `effort-estimator` | Schätzt Aufwände für Entwicklungsaufgaben basierend auf Task-Typ, LLM-Kali |

| `explorer` | Read-only Codebase-Recherche, Dependency, Impact-Mapping |

| `export-manager` | Target-agnostischer Output-Router: Markdown, Confluence, Jira-Xray |

| `feedback` | Projekt-Feedback standardisieren: Bugs, Features, Verbesserungen als GitHub I |

| `frontend-component-engineer` | Screen-Spec + Token-Contract → produktionsreife UI-Komponenten |

| `frontend-reviewer` | Frontend-Domain-Review: Komponenten, State, SSR/Hydration |

| `gemini-expert` | Absoluter Analyse-Experte für die Plattform Gemini (Antigravity): Funktionswe |

| `git` | Commits, Branches, Tags |

| `ideation` | Neue Ideen explorieren, Vision schärfen, Übergabe an requirements |

| `incident-responder` | Live-Incident-Koordination: korreliert Logs, Metriken, führt Runbook-Schri |

| `intern-developer` | Der übereifrige Praktikant |

| `log-analyzer` | System, Applikations-Logs analysieren: Frequency-Clustering, Severity-Kla |

| `mammouth-expert` | Absoluter Analyse-Experte für die Plattform Mammouth Code: Funktionsweise, Ko |

| `meta-feedback` | Verbesserungsvorschläge für agent-meta als GitHub Issues einreichen |

| `opencode-expert` | Absoluter Analyse-Experte für die Plattform Opencode: Funktionsweise, Konfigu |

| `openscad-developer` | Parametrische 3D-Modelle in OpenSCAD generieren, Render-Inspect-Refine via MC |

| `orchestrator` | Einstiegspunkt für alle Entwicklungsaufgaben |

| `performance-optimizer` | Big-O Bottleneck-Identifikation, datengetriebene Performance-Optimierung |

| `planner` | Umsetzungsplanung |

| `product-manager` | Strategisches Produkt-Management: Backlog, User-Stories, Sprint-Planung |

| `prompt-engineer` | Der ultimative Experte für Prompt-Engineering |

| `prompt-governor` | Prompt-Governance: PromptBOM, Audit-Trail, Provenance |

| `proofreader` | Korrektorat: reine Fehlerkorrektur — Rechtschreibung, Grammatik, Zeichensetzung |

| `refactoring-specialist` | Systematische großflächige Code-Transformation mit Sicherheitsnetz: Strangler |

| `release` | Versioning, Changelog, Build-Artifact |

| `requirements` | Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen |

| `security-auditor` | Sicherheits-Audit: OWASP, Secrets, Dependencies |

| `sre-engineer` | Proaktive Reliability-Disziplin: SLI/SLO-Definition, Error-Budgets, Capacity |

| `technical-writer` | Externe entwickler, nutzergerichtete Doku: API-Referenzen, Getting-Starte |

| `test-executor` | Bestehende Test-Suiten ausführen — kein Test-Design, kein Code-Schreiben |

| `tester` | TDD, Test-Suite ausführen, Testabdeckung sichern |

| `ui-reviewer` | UI-Review: Design-Token-Conformance, Layout-Konsistenz, Interaction-States |

| `ui-ux-designer` | UI-Spezifikationen, Mockups, Design-Systeme erstellen |




<!-- agent-meta:managed-end -->

## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!
