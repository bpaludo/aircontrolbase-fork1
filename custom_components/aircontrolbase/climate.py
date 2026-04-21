"""Climate platform for AirControlBase integration."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import SWING_OFF, SWING_ON
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .api import AirControlBaseAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AirControlBase climate platform."""
    api: AirControlBaseAPI = hass.data[DOMAIN][config_entry.entry_id]["api"]
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    refresh_delay: int = hass.data[DOMAIN][config_entry.entry_id]["refresh_delay"]

    async_add_entities(
        AirControlBaseClimate(api, coordinator, device, refresh_delay)
        for device in coordinator.data
    )


class AirControlBaseClimate(CoordinatorEntity, ClimateEntity):
    """Representation of an AirControlBase climate device."""

    def __init__(
        self,
        api: AirControlBaseAPI,
        coordinator: DataUpdateCoordinator,
        device: dict[str, Any],
        refresh_delay: int,
    ) -> None:
        """Initialize the climate device."""
        super().__init__(coordinator)
        self._api = api
        self._device_id = str(device["id"])
        self._refresh_delay = refresh_delay
        self._optimistic_window = max(5, min(refresh_delay, 15))
        self._last_command_time = 0.0
        self._local_device_state: dict[str, Any] | None = None
        self._refresh_task: asyncio.Task | None = None
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}"
        self._attr_name = device["name"]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
        )
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_precision = PRECISION_WHOLE
        self._attr_target_temperature_step = 1
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
        ]
        self._attr_min_temp = 16
        self._attr_max_temp = 30
        self._attr_fan_modes = ["auto", "low", "medium", "high"]
        self._attr_swing_modes = [SWING_ON, SWING_OFF]

    def _should_use_optimistic_state(self) -> bool:
        """Return whether local optimistic state should still be shown."""
        return (
            self._local_device_state is not None
            and (time.time() - self._last_command_time) < self._optimistic_window
        )

    def _find_coordinator_device(self) -> dict[str, Any]:
        """Return the latest device data from the coordinator."""
        for device in self.coordinator.data or []:
            if str(device.get("id")) == self._device_id:
                return device

        _LOGGER.error("Device with ID %s not found in coordinator data", self._device_id)
        return {}

    @property
    def _device(self) -> dict[str, Any]:
        """Return the best available device state."""
        if self._should_use_optimistic_state():
            _LOGGER.debug("Using optimistic state for device %s", self._device_id)
            return self._local_device_state or {}

        self._local_device_state = None
        return self._find_coordinator_device()

    def _apply_optimistic_state(
        self,
        device_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Overlay recent local changes onto a device state."""
        if not self._should_use_optimistic_state() or not self._local_device_state:
            return device_state

        merged_state = device_state.copy()
        merged_state.update(self._local_device_state)
        return merged_state

    async def _async_build_control_context(self) -> dict[str, Any]:
        """Build the freshest full control context expected by the upstream API."""
        fallback_state = self._find_coordinator_device().copy()

        try:
            devices = await self._api.get_details()
        except Exception as err:
            _LOGGER.warning(
                "Could not refresh AirControlBase state before command for device %s. "
                "Using coordinator state instead: %s",
                self._device_id,
                err,
            )
            return self._apply_optimistic_state(fallback_state)

        for device in devices:
            if str(device.get("id")) == self._device_id:
                return self._apply_optimistic_state(device.copy())

        _LOGGER.warning(
            "Device %s was not found in fresh AirControlBase state before command. "
            "Using coordinator state instead.",
            self._device_id,
        )
        return self._apply_optimistic_state(fallback_state)

    def _remember_local_change(
        self,
        base_state: dict[str, Any],
        updates: dict[str, Any],
    ) -> None:
        """Store a short-lived optimistic state after a command."""
        self._last_command_time = time.time()
        self._local_device_state = base_state.copy()
        self._local_device_state.update(updates)

    def _schedule_delayed_refresh(self) -> None:
        """Refresh coordinator state after the cloud has had time to apply the command."""
        if not self.hass:
            return

        if self._refresh_task is not None:
            self._refresh_task.cancel()

        self._refresh_task = self.hass.async_create_task(self._async_delayed_refresh())

    async def _async_delayed_refresh(self) -> None:
        """Refresh the entity after the configured command delay."""
        try:
            await asyncio.sleep(self._refresh_delay)
            await self.coordinator.async_request_refresh()
        except asyncio.CancelledError:
            return
        finally:
            self._refresh_task = None

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.get("factTemp")

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._device.get("setTemp")

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        if not self.is_on:
            return HVACMode.OFF

        mode = self._device.get("mode")
        if mode == "cool":
            return HVACMode.COOL
        if mode == "heat":
            return HVACMode.HEAT
        if mode == "dry":
            return HVACMode.DRY
        if mode in ("fan", "fan_only"):
            return HVACMode.FAN_ONLY
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running HVAC operation."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if self.hvac_mode == HVACMode.DRY:
            return HVACAction.DRYING
        return HVACAction.FAN

    @property
    def is_on(self) -> bool:
        """Return whether the device is on."""
        return self._device.get("power") == "y"

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode."""
        mode = self._device.get("wind")
        return "medium" if mode == "mid" else mode

    @property
    def fan_modes(self) -> list[str]:
        """Return the list of available fan modes."""
        return ["auto", "low", "medium", "high"]

    @property
    def swing_mode(self) -> str:
        """Return the current swing mode."""
        swing = str(self._device.get("swing") or "").strip().lower()
        if swing and swing not in ("0", "off", "n", "no", "false"):
            return SWING_ON
        return SWING_OFF

    @property
    def swing_modes(self) -> list[str]:
        """Return the list of available swing modes."""
        return [SWING_ON, SWING_OFF]

    @property
    def icon(self) -> str:
        """Return the icon for the entity."""
        return "mdi:air-conditioner"

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            _LOGGER.error("No temperature provided to set_temperature")
            return

        control_data = await self._async_build_control_context()
        operation_data = {
            "setTemp": int(temperature),
            "power": "y",
        }

        try:
            self._remember_local_change(control_data, operation_data)
            await self._api.control_device(control_data, operation_data)
            _LOGGER.info(
                "Successfully set temperature to %s for device %s",
                temperature,
                self._device_id,
            )
            self.async_write_ha_state()
            self._schedule_delayed_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set temperature for device %s: %s", self._device_id, err)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target HVAC mode."""
        mode_map = {
            HVACMode.OFF: "off",
            HVACMode.COOL: "cool",
            HVACMode.HEAT: "heat",
            HVACMode.DRY: "dry",
            HVACMode.FAN_ONLY: "fan",
        }

        operation_data: dict[str, Any]
        if hvac_mode == HVACMode.OFF:
            # The cloud keeps the last operating mode while the unit is off.
            # Sending only power mirrors the M-Control integration and avoids
            # introducing a synthetic "off" mode that the API may ignore.
            operation_data = {"power": "n"}
        else:
            target_mode = mode_map[hvac_mode]
            operation_data = {"mode": target_mode, "power": "y"}

        try:
            control_data = await self._async_build_control_context()
            if hvac_mode != HVACMode.OFF and control_data.get("power") == "n":
                operation_data["wind"] = "auto"

            self._remember_local_change(control_data, operation_data)
            await self._api.control_device(control_data, operation_data)
            self.async_write_ha_state()
            self._schedule_delayed_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set HVAC mode for device %s: %s", self._device_id, err)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        if fan_mode not in ["low", "medium", "high", "auto"]:
            _LOGGER.error("Invalid fan mode %s for device %s", fan_mode, self._device_id)
            return

        api_mode = "mid" if fan_mode == "medium" else fan_mode
        operation_data = {"wind": api_mode}

        try:
            control_data = await self._async_build_control_context()
            if control_data.get("power") == "y":
                operation_data["power"] = "y"

            self._remember_local_change(control_data, operation_data)
            await self._api.control_device(control_data, operation_data)
            self.async_write_ha_state()
            self._schedule_delayed_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set fan mode for device %s: %s", self._device_id, err)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode."""
        if swing_mode not in [SWING_ON, SWING_OFF]:
            _LOGGER.error("Invalid swing mode %s for device %s", swing_mode, self._device_id)
            return

        operation_data = {"swing": "1" if swing_mode == SWING_ON else "0"}

        try:
            control_data = await self._async_build_control_context()
            self._remember_local_change(control_data, operation_data)
            await self._api.control_device(control_data, operation_data)
            self.async_write_ha_state()
            self._schedule_delayed_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set swing mode for device %s: %s", self._device_id, err)
