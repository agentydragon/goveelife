"""Mixin classes for Govee Life entities."""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any, Optional

from homeassistant.const import STATE_OFF, STATE_ON

from .api import GoveeApiClient, GoveeDeviceApiClient
from .models import CapabilityType, Device

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class GoveeApiMixin:
    """Mixin to add Govee API functionality to entities."""

    # These should be defined by the entity class
    hass: HomeAssistant
    _entry_id: str
    _device_cfg: dict[str, Any]
    _state_mapping_set: dict[str, int]
    log_prefix: str

    @cached_property
    def _api_client(self) -> GoveeApiClient:
        """Get API client instance."""
        return GoveeApiClient(self.hass, self._entry_id)

    @cached_property
    def _device(self) -> Device:
        """Get device model."""
        return Device(**self._device_cfg)

    @cached_property
    def _device_api(self) -> GoveeDeviceApiClient:
        """Get device-specific API client."""
        return GoveeDeviceApiClient(self._api_client, self._device)

    def _get_cached_value(self, cap_type: CapabilityType, instance: str) -> Any:
        """Get cached capability value."""
        return self._device_api.get_cached_value(cap_type, instance)

    async def _set_power_state(self, turn_on: bool) -> bool:
        """Set device power state."""
        state_key = STATE_ON if turn_on else STATE_OFF
        state_name = "on" if turn_on else "off"

        if state_key not in self._state_mapping_set:
            _LOGGER.error(f"{self.log_prefix}{state_key} not in state mapping")
            return False

        try:
            power_value = self._state_mapping_set[state_key]
            if turn_on:
                return await self._device_api.turn_on(power_value)
            else:
                return await self._device_api.turn_off(power_value)
        except Exception as e:
            _LOGGER.error(f"{self.log_prefix}Turn {state_name} failed: {e}")
            return False

    async def _turn_on(self) -> bool:
        """Turn device on."""
        return await self._set_power_state(True)

    async def _turn_off(self) -> bool:
        """Turn device off."""
        return await self._set_power_state(False)

    async def _set_work_mode_from_mapping(self, mode_settings: dict[str, Any]) -> bool:
        """Set work mode from preset mapping."""
        try:
            work_mode = mode_settings["workMode"]
            mode_value = mode_settings.get("modeValue")
            return await self._device_api.set_work_mode(work_mode, mode_value)
        except ValueError:
            # API error - re-raise with context
            raise
        except Exception as e:
            _LOGGER.error(f"{self.log_prefix}Set work mode failed: {e}")
            return False

    async def _set_range_value(self, instance: str, value: float | int) -> bool:
        """Set a range value."""
        try:
            return await self._device_api.set_range_value(instance, value)
        except ValueError:
            # API error - re-raise with context
            raise
        except Exception as e:
            _LOGGER.error(f"{self.log_prefix}Set range value failed: {e}")
            return False

    def _get_power_state(self) -> Optional[str]:
        """Get power state as HOME_ASSISTANT state string."""
        value = self._device_api.get_on_off_value()
        if value is None:
            return None

        # Map from API value to HA state using _state_mapping
        if hasattr(self, "_state_mapping"):
            return self._state_mapping.get(value)

        return None

    def _is_on(self) -> bool:
        """Check if device is on."""
        return self._get_power_state() == STATE_ON
