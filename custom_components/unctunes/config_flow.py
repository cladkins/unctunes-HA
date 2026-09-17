"""Config flow: a base URL and a venue API token."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    UncTunesApiError,
    UncTunesAuthError,
    UncTunesClient,
    UncTunesConnectionError,
)
from .const import (
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(CONF_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_VERIFY_SSL, default=True): bool,
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


def _normalise_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


class UncTunesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup."""

    VERSION = 1

    async def _async_validate(
        self, base_url: str, token: str, verify_ssl: bool
    ) -> tuple[dict[str, Any] | None, str | None]:
        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        client = UncTunesClient(session, base_url, token, verify_ssl=verify_ssl)
        try:
            venue = await client.async_identify()
        except UncTunesAuthError:
            return None, "invalid_auth"
        except UncTunesConnectionError:
            return None, "cannot_connect"
        except UncTunesApiError as err:
            _LOGGER.warning("UncTunes at %s answered %s: %s", base_url, err.status, err.message)
            return None, "cannot_connect" if err.status == 404 else "unknown"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating UncTunes at %s", base_url)
            return None, "unknown"
        return venue, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = _normalise_url(user_input[CONF_BASE_URL])
            token = user_input[CONF_TOKEN].strip()
            verify_ssl = bool(user_input.get(CONF_VERIFY_SSL, True))
            venue, error = await self._async_validate(base_url, token, verify_ssl)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(venue["id"])
                self._abort_if_unique_id_configured(
                    updates={CONF_BASE_URL: base_url, CONF_TOKEN: token}
                )
                return self.async_create_entry(
                    title=venue.get("name") or venue["slug"],
                    data={
                        CONF_BASE_URL: base_url,
                        CONF_TOKEN: token,
                        CONF_VERIFY_SSL: verify_ssl,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            venue, error = await self._async_validate(
                entry.data[CONF_BASE_URL], token, entry.data.get(CONF_VERIFY_SSL, True)
            )
            if error:
                errors["base"] = error
            elif venue["id"] != entry.unique_id:
                errors["base"] = "wrong_venue"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"venue": entry.title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return UncTunesOptionsFlow()


class UncTunesOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
