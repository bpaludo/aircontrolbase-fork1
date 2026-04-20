"""The AirControlBase integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AirControlBaseAPI,
    AirControlBaseAuthError,
    AirControlBaseConnectionError,
    AirControlBaseError,
    AirControlBaseRateLimitError,
    AirControlBaseTransientError,
)
from .const import (
    CONF_AVOID_REFRESH_STATUS_ON_UPDATE_IN_MS,
    CONF_REFRESH_DELAY,
    DEFAULT_AVOID_REFRESH_STATUS_ON_UPDATE_IN_MS,
    DEFAULT_REFRESH_DELAY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE]
_MAX_BACKOFF_INTERVAL = timedelta(minutes=5)


class AirControlBaseDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator responsible for polling device state."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: AirControlBaseAPI,
        refresh_delay: int,
    ) -> None:
        """Initialize the data coordinator."""
        self.api = api
        self._base_interval = timedelta(seconds=refresh_delay)
        self._failure_count = 0
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_method=self._async_update_data,
            update_interval=self._base_interval,
        )

    def _reset_backoff(self) -> None:
        """Return to the configured polling interval after a recovery."""
        if self.update_interval != self._base_interval:
            _LOGGER.info(
                "AirControlBase polling recovered. Restoring interval to %s.",
                self._base_interval,
            )
            self.update_interval = self._base_interval
        self._failure_count = 0

    def _apply_backoff(self, reason: Exception) -> None:
        """Increase the polling interval after repeated transient failures."""
        self._failure_count += 1
        multiplier = min(2 ** self._failure_count, 8)
        next_interval = min(self._base_interval * multiplier, _MAX_BACKOFF_INTERVAL)
        if next_interval != self.update_interval:
            _LOGGER.warning(
                "AirControlBase polling failed (%s). Backing off to %s.",
                reason,
                next_interval,
            )
            self.update_interval = next_interval

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from the API."""
        try:
            devices = await self.api.get_details()
        except AirControlBaseAuthError as err:
            self._failure_count = 0
            raise ConfigEntryAuthFailed("Authentication with AirControlBase expired") from err
        except (
            AirControlBaseTransientError,
            AirControlBaseRateLimitError,
            AirControlBaseConnectionError,
        ) as err:
            self._apply_backoff(err)
            raise UpdateFailed(f"Temporary AirControlBase failure: {err}") from err
        except AirControlBaseError as err:
            _LOGGER.error("AirControlBase returned a non-recoverable API error: %s", err)
            raise UpdateFailed(f"AirControlBase API error: {err}") from err
        except Exception as err:
            self._apply_backoff(err)
            raise UpdateFailed(f"Unexpected AirControlBase error: {err}") from err

        _LOGGER.debug("Coordinator fetched %s devices", len(devices))
        self._reset_backoff()
        return devices


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AirControlBase from a config entry."""
    refresh_delay = entry.data.get(CONF_REFRESH_DELAY, DEFAULT_REFRESH_DELAY)
    session = async_get_clientsession(hass)
    api = AirControlBaseAPI(
        entry.data["email"],
        entry.data["password"],
        session,
        entry.data.get(
            CONF_AVOID_REFRESH_STATUS_ON_UPDATE_IN_MS,
            DEFAULT_AVOID_REFRESH_STATUS_ON_UPDATE_IN_MS,
        ),
    )

    try:
        await api.login()
    except AirControlBaseRateLimitError as err:
        _LOGGER.warning("AirControlBase rate limited setup login: %s", err)
        raise ConfigEntryNotReady(f"AirControlBase rate limited the setup: {err}") from err
    except AirControlBaseTransientError as err:
        _LOGGER.warning("Temporary AirControlBase error during setup: %s", err)
        raise ConfigEntryNotReady(f"Temporary AirControlBase error: {err}") from err
    except AirControlBaseConnectionError as err:
        _LOGGER.error("Connection error during setup: %s", err)
        raise ConfigEntryNotReady(f"Could not connect to AirControlBase: {err}") from err
    except AirControlBaseAuthError as err:
        _LOGGER.error("Authentication failed during setup: %s", err)
        raise ConfigEntryAuthFailed("Authentication with AirControlBase failed") from err
    except Exception as err:
        _LOGGER.error("Unexpected error during setup: %s", err)
        raise ConfigEntryNotReady(f"Unexpected AirControlBase error: {err}") from err

    coordinator = AirControlBaseDataUpdateCoordinator(hass, api, refresh_delay)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "refresh_delay": refresh_delay,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
