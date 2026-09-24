"""CommandCode config, reauth, reconfigure, and options flows."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

try:  # ``ConfigFlowResult`` was added after the oldest supported HA release.
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:  # pragma: no cover - exercised only on old HA
    ConfigFlowResult = dict  # type: ignore[misc,assignment]
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCOUNT_NAME,
    CONF_ACCOUNT_SCOPE_KEY,
    CONF_ALLOW_CUSTOM_BASE_URL,
    CONF_API_KEY,
    CONF_AUTO_UPDATE_MODELS,
    CONF_AUTO_UPDATE_USAGE,
    CONF_BASE_URL,
    CONF_MODELS_REFRESH_MINUTES,
    CONF_OFFLINE_PENDING,
    CONF_PACE_RED_PERCENT,
    CONF_USAGE_REFRESH_MINUTES,
    CONF_WARN_PERCENT,
    DEFAULT_BASE_URL,
    DEFAULT_MODELS_REFRESH_MINUTES,
    DEFAULT_PACE_RED_PERCENT,
    DEFAULT_USAGE_REFRESH_MINUTES,
    DEFAULT_WARN_PERCENT,
    DOMAIN,
    account_scope_key,
    account_unique_id,
    api_key_unique_id,
    normalize_api_key,
    validate_base_url,
)
from .coordinator import CommandCodeApiClient, CommandCodeApiError, parse_whoami

_OPTIONS_FLOW_BASE = getattr(
    config_entries,
    "OptionsFlowWithConfigEntry",
    config_entries.OptionsFlow,
)


def _api_key_schema() -> selector.TextSelector:
    """Return a masked API-key selector for Home Assistant UI flows."""
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )


async def _probe_api_key(
    hass: HomeAssistant,
    api_key: str,
    base_url: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Probe whoami; return a sanitized account or a flow error code."""
    normalized_key = normalize_api_key(api_key)
    if not normalized_key:
        return None, "invalid_token"
    client = CommandCodeApiClient(async_get_clientsession(hass), base_url, normalized_key)
    try:
        account = parse_whoami(await client.fetch_whoami())
    except CommandCodeApiError as err:
        if err.status == 401:
            return None, "invalid_token"
        if err.status == 403:
            return None, "forbidden"
        return None, "cannot_connect"
    except (TimeoutError, aiohttp.ClientError):
        return None, "cannot_connect"
    except Exception:  # noqa: BLE001
        return None, "cannot_connect"
    return (account, None) if account is not None else (None, "invalid_response")


def _user_schema(
    account_name: str = "",
    base_url: str = DEFAULT_BASE_URL,
    api_key: str = "",
    include_skip_validation: bool = True,
) -> vol.Schema:
    """Build the user/reconfigure schema without echoing a stored secret."""
    fields: dict[Any, Any] = {
        vol.Required(CONF_ACCOUNT_NAME, default=account_name): str,
        vol.Required(CONF_API_KEY, default=api_key): _api_key_schema(),
        vol.Optional(CONF_BASE_URL, default=base_url): str,
    }
    if include_skip_validation:
        fields[vol.Required("skip_validation", default=False)] = bool
    return vol.Schema(fields)


def _identity_data(
    account_name: str,
    api_key: str,
    base_url: str,
    account: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build entry data without ever storing a raw provider identity."""
    data: dict[str, Any] = {
        CONF_ACCOUNT_NAME: account_name,
        CONF_API_KEY: api_key,
        CONF_BASE_URL: base_url,
        CONF_OFFLINE_PENDING: account is None,
    }
    scope = account_scope_key(account) if account is not None else None
    if scope:
        data[CONF_ACCOUNT_SCOPE_KEY] = scope
    return data


class CommandGaugeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Configure one CommandCode billing account per config entry."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._reauth_entry: ConfigEntry | None = None
        self._reconfigure_entry: ConfigEntry | None = None

    def _context_entry(self) -> ConfigEntry | None:
        """Resolve a flow entry from the context on old and new HA versions."""
        entry_id = self.context.get("entry_id")
        if not entry_id:
            return None
        return self.hass.config_entries.async_get_entry(entry_id)

    def _update_entry_and_abort(
        self,
        entry: ConfigEntry,
        *,
        data: dict[str, Any],
        reason: str,
        unique_id: str | None = None,
    ) -> ConfigFlowResult:
        """Update and reload an entry, with a compatibility fallback."""
        update: dict[str, Any] = {"data": data}
        if unique_id is not None:
            update["unique_id"] = unique_id
        reload_and_abort = getattr(self, "async_update_reload_and_abort", None)
        if callable(reload_and_abort):
            return reload_and_abort(entry, reason=reason, **update)
        update_and_abort = getattr(self, "async_update_and_abort", None)
        if callable(update_and_abort):
            return update_and_abort(entry, reason=reason, **update)
        self.hass.config_entries.async_update_entry(entry, **update)
        schedule_reload = getattr(self.hass.config_entries, "async_schedule_reload", None)
        if callable(schedule_reload):
            schedule_reload(entry.entry_id)
        return self.async_abort(reason=reason)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Create an entry; network failures are explicitly non-blocking."""
        values = user_input or {}
        errors: dict[str, str] = {}
        account_name = str(values.get(CONF_ACCOUNT_NAME, "")).strip()
        raw_api_key = values.get(CONF_API_KEY, "")
        api_key = normalize_api_key(raw_api_key) or ""
        base_url = str(values.get(CONF_BASE_URL, DEFAULT_BASE_URL)).strip() or DEFAULT_BASE_URL
        allow_custom = bool(values.get(CONF_ALLOW_CUSTOM_BASE_URL, False))
        try:
            base_url = validate_base_url(base_url, allow_custom=allow_custom)
        except ValueError:
            errors["base"] = "invalid_base_url"
        skip_validation = bool(values.get("skip_validation", False))

        if user_input is not None:
            if not account_name or not api_key:
                errors["base"] = "missing_fields"
            elif not errors:
                account: dict[str, Any] | None = None
                error: str | None = None
                if not skip_validation:
                    account, error = await _probe_api_key(self.hass, api_key, base_url)
                    if error in {"invalid_token", "invalid_response", "forbidden"}:
                        errors["base"] = error
                if not errors:
                    unique_id = (
                        account_unique_id(account)
                        if account is not None
                        else api_key_unique_id(api_key)
                    )
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    title = f"Command Gauge {account_name}"
                    if error == "cannot_connect":
                        title += " ⚠️ offline gespeichert"
                    return self.async_create_entry(
                        title=title,
                        data=_identity_data(account_name, api_key, base_url, account),
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(account_name, base_url),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> ConfigFlowResult:
        self._reauth_entry = self._context_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="reauth_failed")
        errors: dict[str, str] = {}
        api_key = normalize_api_key((user_input or {}).get(CONF_API_KEY, "")) or ""
        if user_input is not None:
            if not api_key:
                errors["base"] = "missing_fields"
            else:
                account: dict[str, Any] | None = None
                base_url = str(entry.data.get(CONF_BASE_URL) or DEFAULT_BASE_URL)
                try:
                    base_url = validate_base_url(base_url, allow_custom=False)
                except ValueError:
                    errors["base"] = "invalid_base_url"
                if not errors:
                    account, error = await _probe_api_key(self.hass, api_key, base_url)
                    if error:
                        errors["base"] = error
                if errors:
                    pass
                else:
                    scope = account_scope_key(account or {})
                    stored_scope = entry.data.get(CONF_ACCOUNT_SCOPE_KEY)
                    if stored_scope and scope and scope != stored_scope:
                        return self.async_abort(reason="wrong_account")
                    new_data = {**entry.data, CONF_API_KEY: api_key, CONF_OFFLINE_PENDING: False}
                    if scope:
                        new_data[CONF_ACCOUNT_SCOPE_KEY] = scope
                    # Keep the original entry unique ID stable. A legacy offline
                    # entry may be migrated only when the target scope is unused.
                    if entry.unique_id != scope:
                        existing = self.hass.config_entries.async_entry_for_domain_unique_id(
                            DOMAIN, scope
                        )
                        if existing is not None and existing.entry_id != entry.entry_id:
                            return self.async_abort(reason="already_configured")
                        # Only a legacy/offline entry may be migrated, and only once.
                        if entry.unique_id and not entry.data.get(CONF_OFFLINE_PENDING, False):
                            return self.async_abort(reason="wrong_account")
                    return self._update_entry_and_abort(
                        entry,
                        data=new_data,
                        reason="reauth_successful",
                        unique_id=scope if entry.data.get(CONF_OFFLINE_PENDING, False) else None,
                    )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): _api_key_schema()}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self._reconfigure_entry
        if entry is None:
            entry = self._context_entry()
            self._reconfigure_entry = entry
        if entry is None:
            return self.async_abort(reason="reconfigure_failed")
        errors: dict[str, str] = {}
        values = user_input or {}
        account_name = str(
            values.get(CONF_ACCOUNT_NAME, entry.data.get(CONF_ACCOUNT_NAME, ""))
        ).strip()
        raw_api_key = values.get(CONF_API_KEY, "")
        api_key = normalize_api_key(raw_api_key) or ""
        base_url = (
            str(values.get(CONF_BASE_URL, entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL))).strip()
            or DEFAULT_BASE_URL
        )
        if user_input is not None:
            if not account_name or not api_key:
                errors["base"] = "missing_fields"
            else:
                account: dict[str, Any] | None = None
                try:
                    base_url = validate_base_url(base_url, allow_custom=False)
                except ValueError:
                    errors["base"] = "invalid_base_url"
                if not errors:
                    account, error = await _probe_api_key(self.hass, api_key, base_url)
                    if error:
                        errors["base"] = error
                if errors:
                    pass
                else:
                    scope = account_scope_key(account or {})
                    stored_scope = entry.data.get(CONF_ACCOUNT_SCOPE_KEY)
                    if stored_scope and scope and scope != stored_scope:
                        return self.async_abort(reason="wrong_account")
                    new_data = {
                        CONF_ACCOUNT_NAME: account_name,
                        CONF_API_KEY: api_key,
                        CONF_BASE_URL: base_url,
                        CONF_OFFLINE_PENDING: False,
                    }
                    if scope:
                        new_data[CONF_ACCOUNT_SCOPE_KEY] = scope
                    if entry.unique_id != scope:
                        existing = self.hass.config_entries.async_entry_for_domain_unique_id(
                            DOMAIN, scope
                        )
                        if existing is not None and existing.entry_id != entry.entry_id:
                            return self.async_abort(reason="already_configured")
                        if entry.unique_id and not entry.data.get(CONF_OFFLINE_PENDING, False):
                            return self.async_abort(reason="wrong_account")
                    return self._update_entry_and_abort(
                        entry,
                        data=new_data,
                        reason="reconfigure_successful",
                        unique_id=scope if entry.data.get(CONF_OFFLINE_PENDING, False) else None,
                    )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(account_name, base_url, include_skip_validation=False),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return CommandGaugeOptionsFlowHandler(config_entry)


class CommandGaugeOptionsFlowHandler(_OPTIONS_FLOW_BASE):
    """Edit polling cycles, thresholds, and the display name."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__(config_entry)

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            values = dict(user_input)
            account_name = str(values.pop(CONF_ACCOUNT_NAME, "")).strip()
            warn_percent = int(values.get(CONF_WARN_PERCENT, DEFAULT_WARN_PERCENT))
            red_percent = int(values.get(CONF_PACE_RED_PERCENT, DEFAULT_PACE_RED_PERCENT))
            if red_percent < warn_percent:
                errors["base"] = "invalid_thresholds"
            elif not account_name:
                errors["base"] = "missing_fields"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_ACCOUNT_NAME: account_name},
                    options=values,
                )
                return self.async_create_entry(title="", data=values)

        options = entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT_NAME, default=entry.data.get(CONF_ACCOUNT_NAME, "")): str,
                vol.Required(
                    CONF_WARN_PERCENT, default=options.get(CONF_WARN_PERCENT, DEFAULT_WARN_PERCENT)
                ): vol.All(int, vol.Range(min=1, max=100)),
                vol.Required(
                    CONF_PACE_RED_PERCENT,
                    default=options.get(CONF_PACE_RED_PERCENT, DEFAULT_PACE_RED_PERCENT),
                ): vol.All(int, vol.Range(min=1, max=1000)),
                vol.Required(
                    CONF_AUTO_UPDATE_USAGE, default=options.get(CONF_AUTO_UPDATE_USAGE, True)
                ): bool,
                vol.Required(
                    CONF_USAGE_REFRESH_MINUTES,
                    default=options.get(CONF_USAGE_REFRESH_MINUTES, DEFAULT_USAGE_REFRESH_MINUTES),
                ): vol.All(int, vol.Range(min=5, max=1440)),
                vol.Required(
                    CONF_AUTO_UPDATE_MODELS, default=options.get(CONF_AUTO_UPDATE_MODELS, True)
                ): bool,
                vol.Required(
                    CONF_MODELS_REFRESH_MINUTES,
                    default=options.get(
                        CONF_MODELS_REFRESH_MINUTES, DEFAULT_MODELS_REFRESH_MINUTES
                    ),
                ): vol.All(int, vol.Range(min=60, max=1440)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
