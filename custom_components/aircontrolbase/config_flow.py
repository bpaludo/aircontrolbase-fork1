"""Config flow for AirControlBase integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .api import (
    AirControlBaseAPI,
    AirControlBaseAuthError,
    AirControlBaseConnectionError,
    AirControlBaseRateLimitError,
    AirControlBaseTransientError,
)
from .const import DEFAULT_REFRESH_DELAY, CONF_REFRESH_DELAY, DOMAIN

_LOGGER = logging.getLogger(__name__)

class AirControlBaseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AirControlBase."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                session = aiohttp_client.async_get_clientsession(self.hass)
                api = AirControlBaseAPI(
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                    session,
                )

                _LOGGER.debug("Testing authentication for: %s", user_input[CONF_EMAIL])

                await api.test_connection()
                _LOGGER.info("Authentication successful for: %s", user_input[CONF_EMAIL])
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data=user_input,
                )
            except (AirControlBaseTransientError, AirControlBaseRateLimitError) as err:
                _LOGGER.warning("Temporary AirControlBase failure during config flow: %s", err)
                errors["base"] = "cannot_connect"
            except AirControlBaseConnectionError as err:
                _LOGGER.error("Connection failed: %s", err)
                errors["base"] = "cannot_connect"
            except AirControlBaseAuthError as err:
                _LOGGER.error("Authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.error("Unexpected error: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_REFRESH_DELAY, default=DEFAULT_REFRESH_DELAY): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                }
            ),
            errors=errors,
        )
