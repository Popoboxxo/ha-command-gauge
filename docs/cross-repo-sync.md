# Cross-Repo-Sync: ha-command-gauge ↔ ha-go-gauge

Stand: 2026-10-04 · Gilt für: beide Repos (`ha-command-gauge`, `ha-go-gauge`)

Dieses Dokument ist der **operative Teil** der Parität: `docs/parity-with-go-gauge.md`
beschreibt *was* gleich ist und wo die Differenzen liegen — hier steht *wie* die
Synchronität bei jeder Änderung hergestellt und geprüft wird.

## Grundregel

> Jede user-facing Änderung an einer Integration ist ein **Paar-Change**:
> sie wird am Schwester-Repo geprüft und, soweit die jeweilige API hergibt,
> gespiegelt. Eine Änderung, die nur in einem Repo landet, braucht eine
> begründete Ausnahme in der Feature-Matrix.

## 1. Change-Management — Paar-Change-Checkliste (vor jedem Merge)

Die Checkliste gilt für jeden PR/Branch, der user-facing Änderungen trägt
(Entities, Coordinator-Verhalten, Options, Flows, Translations, CI-Tools).
Reine Repo-lokale chores (Typos in Doku, Test-Fixtures) sind davon ausgenommen.

**A. Selbstprüfung im eigenen Repo**

- [ ] **Entity-Schema:** `unique_id`-Schema unverändert? Kein hartcodiertes
      `_attr_name`/`name`-Literal (nur `_attr_has_entity_name` +
      `_attr_translation_key`)?
- [ ] **Translations:** `strings.json` (englischer Master) erweitert,
      `translations/de.json` + `en.json` vollständig mitgepflegt?
      `python scripts/check_json_consistency.py` grün?
- [ ] **Naming:** Neue `translation_key`s/Options-Konstanten/Coordinator-
      Attribute nach Möglichkeit am Namensschema des Schwester-Repos
      ausgerichtet (siehe Matrix, Abschnitt „Naming parallel halten")?
- [ ] **Tests:** Test im selben Typ wie das go_gauge-/command_gauge-
      Gegenstück (Wiring-Test, Parser-Test, CI-Skript-Test)?

**B. Spiegel-Prüfung am Schwester-Repo (Read-only — siehe Abschnitt 6)**

- [ ] Betroffene Datei im 1:1-Mapping der Matrix gefunden
      (`entity.py`↔`entity.py`, `coordinator.py`↔`coordinator.py`, …)?
- [ ] Ist die Änderung dort **übertragbar** (API liefert Äquivalent)?
      → Ja: als Todo/Eintrag für das Schwester-Repo festhalten, idealerweise
      direkt als Issue in beiden Repos verlinkt.
      → Nein: **Begründung** in der Feature-Matrix als ⚠️-Eintrag mit
      Schließungsbedingung nachtragen.
- [ ] **Feature-Matrix** (`docs/parity-with-go-gauge.md`) im selben Branch
      aktualisiert: neue Zeile oder Status geändert, Abweichung begründet?

**C. Merge-Freigabe**

- [ ] Matrix-Update ist Teil des Commits (Docs-Commit im selben Branch).
- [ ] Kein ❌/⚠️-Eintrag ohne Begründung und Schließungsbedingung.

## 2. Auslöser & Rollen — wer erkennt Drift?

| Mechanismus | Wo | Wer | Frequenz |
|---|---|---|---|
| **Matrix-Prüfung als Release-Schritt** | beide Repos, vor dem Tag | die releaseführende Rolle (`release`/User) | jedes Release |
| **Paar-Change-Checkliste** | im Change selbst | der implementierende Entwickler/Agent | jeder user-facing PR |
| **CI-Regression im eigenen Repo** | `validate.yml` | CI | jeder Push |
| **Matrix-Nachführen bei API-Differenzen** | Doku | siehe Abschnitt 4 | bei jedem neuen API-Feld |

- **CI kann Cross-Repo-Drift nicht direkt messen** (getrennte Repos,
  Repo-Containment) — die CI-Tools (`check_json_consistency.py`,
  `check_version_sync.py`) sind deshalb **ports-identisch** in beiden Repos
  und fangen Drift indirekt ab: Wer ein Tool ändert, muss den Port
  mitschleifen (Checkliste A + Matrix, Abschnitt „Werkzeuge synchron halten").
- **Trigger ist die manuelle Matrix-Prüfung pro Release**, nicht ein
  Automatismus: Vor jedem Tag wird die Matrix Zeile für Zeile gegen den
  Ist-Stand des eigenen Repos gelesen und vermerkt, dass der Abgleich
  erfolgt ist (z. B. Zeile im CHANGELOG-Eintrag „parity matrix reviewed").

## 3. Versions-Disziplin

- **Unabhängige SemVer je Repo** — es gibt kein gemeinsames Versionsschema.
- **Gespiegelte Features → parallele Minor-Releases:** Landet ein Feature
  als Spiegelung in beiden Repos, erfolgen beide Releases im selben Zyklus
  (nicht zeitlich streng gekoppelt, aber ohne zwischenliegendes
  „ein Repo hat es, das andere nicht"-Fenster über ein Minor-Release hinaus).
- **PATCH darf repo-lokal sein**, wenn die Änderung anbieterspezifisch ist
  (z. B. CommandCode-API-Feldumbenennung, go_gauge-Workspace-Bugfix).
- **Kein Tag/Release ohne Matrix-Abgleich:** Der Release-Check in
  `scripts/check_version_sync.py` sichert Tag ↔ `manifest.version`; den
  Matrix-Abgleich sichert der Release-Schritt aus Abschnitt 2. Beide gehören
  fest zum Release-Dreiklang (AGENTS.md: Commit → Tag → echtes Release).
- **Entity-Breaking = MAJOR** in dem Repo, in dem es passiert — und als
  solches in der Matrix vermerkt, weil es indirekt auch die Spiegelung
  betrifft.

## 4. API-blockierte Differenzen — fester Prüfprozess

Neue API-Felder (oder weggefallene) werden nie ad hoc umgesetzt:

1. **Feld erfassen:** Welches Feld, welche API, welcher Endpunkt, welches
   Payload-Beispiel?
2. **Äquivalenz prüfen:** Liefert die Schwester-API ein semantisches
   Äquivalent? (Beispiele aus der Matrix: Pricing → go_gauge ja /
   command_gauge nein; Workspaces → go_gauge ja / command_gauge nein;
   Monatsfenster → go_gauge ja / command_code nein.)
3. **Entscheid:**
   - *Beide Seiten liefern es* → defensiv parsen, normalisieren, im
     Coordinator-Block anbieten, Sensor/Entity spiegeln, Matrix auf ✅.
   - *Nur eine Seite* → umsetzen **und** Matrix-Eintrag mit ⚠️ +
     konkreter Schließungsbedingung („wenn CommandCode `/provider/v1/models`
     Pricing liefert: `build_models_block` erweitern, go_gauge-Sensoren
     `cheapest_model`/`free_models`/`live_models_count` spiegeln").
4. **Re-Check:** Bei jedem Release des anderen Repos wird die Matrix auf
   „inzwischen umsetzbar?" gelesen — Anbieter-APIs ändern sich, ⚠️-Einträge
   veralten.

## 5. Gemeinsame TODOs — koordinierte Umsetzung

Manche Punkte betreffen beide Repos gleichermaßen (aktueller Fall:
`suggested_object_id`-Pinning, siehe Matrix Abweichung 1). Ablauf:

1. **Issue in beiden Repos anlegen und gegenseitig verlinken** (gleiche
   Beschreibung, gleicher Umfang).
2. **Referenz-Implementierung festlegen** (für das Pinning: Vorbild
   `ha-health-o-mat`, `entity.py`, `HealthOMatEntity.suggested_object_id`
   — *nicht* go_gauge 1.5.2, das es ebenfalls nicht hat).
3. **Reihenfolge:** Umsetzung im zweiten Repo erst nach dem Merge im ersten;
   Test-Stubs (`tests/conftest.py`) in beiden Repos für die verwendeten
   HA-Internals (`platform_data`, `_name_internal`) erweitern.
4. **Migration des Altbestands mitplanen:** command_gauge hat auf der
   Live-Instanz deutsch erstregistrierte Entity-Slugs (CHANGELOG 0.1.1:
   `account_erreichbar`); analog zu go_gauge v6/v7 ist eine Entity-Registry-
   Migration (`er.async_migrate_entries`, nur `entity_id`/`original_name`,
   `unique_id` bleibt) mit `manifest.VERSION`-Bump (→ MAJOR) vorgesehen.
5. **Dev-Instanz-Etikette beachten** (AGENTS.md, „Etikette auf einer
   geteilten Dev-Instanz"): Die Instanz trägt **beide** Domains
   (`command_gauge`, `go_gauge`). Vor der koordinierten Umsetzung
   abstimmen: Systemsprache wechseln und Registry-Migrationen rendern/
   berühren `friendly_name` und ggf. Erstregistrierungen **aller** Domains;
   Resets sind destruktiv instanzweit; `unique_id`s akkumulieren über alle
   Domains hinweg — niemals ändern.

## 6. Session-Praxis — Containment beidseitig

Beide Repos haben **Repo-Containment aktiv** (Schreiben nur in die eigene
Projekt-Wurzel, Ausnahme `.tmp/`). Daraus folgt für die Zusammenarbeit:

- **Eine Session = ein Repo.** Jede Arbeitsession ist in genau einem der
  beiden Repos verwurzelt und darf nur dort schreiben.
- **Das Schwester-Repo ist in jeder Session Read-only** (lesen, vergleichen,
  Matrix dagegen prüfen — niemals schreiben, auch nicht „nur kurz").
- **Änderungen am Schwester-Repo** (z. B. die go_gauge-Seite eines
  Paar-Changes, Port eines CI-Tools) erfolgen ausschließlich in einer
  eigenen Session, die in diesem Repo verwurzelt ist, auf einem eigenen
  Branch (`chore/…`, `feat/…`), mit eigenem Commit — nicht als
  „Mitfahren" in der Session des anderen Repos.
- **Keine Worktree-Isolation, keine Auslagerung** in Infrastruktur-Ordner
  (`.claude/`, `.opencode/` etc.) — gilt je Repo (AGENTS.md,
  „No Worktree Isolation").
- **Tokens/State der einen Integration** werden nie in das andere Repo
  kopiert oder committet.

## Verwandte Dokumente

- `docs/parity-with-go-gauge.md` — Feature-Matrix, Abweichungen mit
  Schließungsbedingungen (Pflege-Objekt der Checkliste aus Abschnitt 1).
- `AGENTS.md` (beide Repos) — eiserne HACS-Regeln, Release-Dreiklang,
  Dev-Instanz-Etikette.
