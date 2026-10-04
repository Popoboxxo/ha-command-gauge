# Changelog

## [0.2.0] - 2026-10-04

Release-readiness and parity release. No breaking changes: no `unique_id`
changed, no ConfigEntry `VERSION` bump, no `async_migrate_entry` needed.

### Added

- **Pace sensor traffic-light icon and threshold attributes** (parity with
  go_gauge): the per-window pace sensor now renders a status-matching icon
  (green `mdi:check-circle-outline`, yellow `mdi:alert-circle-outline`, red
  `mdi:close-circle-outline`, fallback `mdi:speedometer-medium`) and exposes
  `forecast_percent`, `green_below`, and `red_above` as state attributes, so
  dashboards and automations can react to the raw forecast without parsing
  the green/yellow/red string.
- `scripts/check_json_consistency.py` — validates that `manifest.json`,
  `hacs.json`, `strings.json`, and every `translations/*.json` parse and
  that all translations carry exactly the key paths of the English master.
  Runs as a CI step in `validate.yml`.
- `scripts/check_version_sync.py` — enforces the HACS release rule that the
  GitHub release tag and `manifest.json:version` are identical apart from
  the tag's leading `v`. Runs on every published release (CI job
  `release-version-sync`).
- `tests/test_ci_scripts.py` — covers both scripts, including the
  missing/extra translation key and tag mismatch failure paths.

### Fixed

- `pytest` crashed before collecting any test on machines with the globally
  installed `pytest-homeassistant-custom-component` plugin (it imports
  `fcntl`, which does not exist on Windows). The suite installs its own HA
  stubs in `tests/conftest.py` and does not use that plugin, so
  `pyproject.toml` now disables its auto-loading (`-p no:homeassistant`;
  a no-op in CI where the plugin is not installed).

### Verification

53 tests passed, `scripts/check_json_consistency.py` OK,
`scripts/check_version_sync.py` skip-without-tag OK.

## [0.1.1] - 2026-09-26

First bugfix release. Both issues below were found by deploying this
integration to a live Home Assistant 2026.9.1 instance and configuring it
with an API key that does not authenticate — not by unit tests, which
covered neither path.

### Fixed

**"Save without validating" (`skip_validation`) was a dead checkbox.**
`config_flow` stored `CONF_OFFLINE_PENDING: True`, but `async_setup_entry`
never read the key and still called
`async_config_entry_first_refresh()`, which raised
`ConfigEntryAuthFailed`. The form accepted the option and then ignored it:
the entry landed in `setup_error` with *"CommandCode rejected the API key"*
and **no entities at all** — 0 instead of 35.

`async_setup_entry` now honours `offline_pending` and skips the blocking
first refresh for that entry only. Everything else keeps its fail-closed
behaviour: a validated entry still raises on a bad key, and a malformed
base URL still blocks with `ConfigEntryNotReady` regardless of the flag,
because that is a typo and not a temporary outage.

**An authentication failure never reached the UI.** The coordinator logged a
perfectly clear error while every entity reported a bare `unknown`:

```
ERROR [custom_components.command_gauge.coordinator] Authentication failed
while fetching command_gauge data: CommandCode rejected the API key
```

Two independent causes:

1. `_raise_auth(err)` was called *before* `statuses[section] = ...`, so the
   section status was never computed for an auth failure. Reordered in all
   five call sites (`models`, `account`, `credits`, `subscription`, `usage`).
2. Home Assistant assigns `self.data = await self._async_update_data()` — an
   exception therefore leaves the coordinator on its previous snapshot, so a
   correctly computed status would still never have been published.
   `_async_update_data` now catches `ConfigEntryAuthFailed` / `UpdateFailed`,
   publishes the collected statuses to `self.data`, and re-raises, so HA
   still gets the reauth signal.

Observed before and after, same instance, same invalid key:

| | before | after |
|---|---|---|
| `account_erreichbar` | `unknown` | `off` |
| 23 data sensors | `unknown` | `unavailable` |

`account_erreichbar` is the one entity that keeps reporting: it deliberately
stays `available` so it can show *why* the data is missing. The error code
(`http_401`, `network`, `schema_unrecognized`) and `last_attempt_at` are
recorded per section.

### Added

- `tests/test_offline_pending_setup.py` — 6 tests for the offline-pending
  path, including the fail-closed counter-cases.
- `tests/test_coordinator_error_status.py` — 5 tests asserting the status is
  published for auth, schema and network failures, and that the reauth
  signal is not swallowed.
- `ConfigEntryNotReady` added to the offline HA stub in `tests/conftest.py`
  (it was missing entirely, so `pytest.raises` could not be used on it).

### Verification

36 tests passed, `ruff check` clean, `E501` clean, `compileall` clean.
Both fixes were re-checked by reverting each one in isolation and confirming
the corresponding tests fail (offline-pending: 1 failure; coordinator: 3).
E2E on Home Assistant 2026.9.1: 35 entities created across all five
platforms, error path confirmed live.

No breaking changes: no `unique_id` changed, no ConfigEntry `VERSION` bump,
no `async_migrate_entry` needed.
