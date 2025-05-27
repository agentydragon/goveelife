"""Cache management for Govee device states."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from homeassistant.const import CONF_STATE
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .models import CapabilityType, DeviceStateResponse

_LOGGER = logging.getLogger(__name__)


@dataclass
class GoveeStateCache:
    """Manages cached device states."""

    hass: HomeAssistant
    entry_id: str

    @property
    def _states(self) -> dict[str, dict[str, Any]]:
        """Get states dictionary, creating if needed."""
        return self.hass.data[DOMAIN][self.entry_id].setdefault(CONF_STATE, {})

    def __getitem__(self, device_id: str) -> Optional[DeviceStateResponse]:
        """Get cached state for a device as Pydantic model."""
        if not (state_data := self._states.get(device_id)):
            return None

        try:
            return DeviceStateResponse(**state_data)
        except Exception:
            _LOGGER.error(f"Failed to parse cached state for {device_id}")
            return None

    def __setitem__(self, device_id: str, state: DeviceStateResponse) -> None:
        """Cache device state data."""
        self._states[device_id] = state.model_dump(by_alias=True)

    def get_capability_value(
        self, device_id: str, cap_type: CapabilityType, instance: str
    ) -> Any:
        """Get cached value for a specific capability."""
        state = self[device_id]
        return state.get_capability_value(cap_type, instance) if state else None
