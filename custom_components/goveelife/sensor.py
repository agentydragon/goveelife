"""Sensor entities for the Govee Life integration."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Final

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICES, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_COORDINATORS, DOMAIN
from .entities import GoveeLifePlatformEntity
from .mixins import GoveeApiMixin
from .models import CapabilityType

_LOGGER: Final = logging.getLogger(__name__)

PLATFORM: Final = "sensor"
PLATFORM_DEVICE_TYPES: Final = [
    "devices.types.sensor:.*",
    "devices.types.thermometer:.*",
    "devices.types.air_purifier:.*property.*",
    "devices.types.dehumidifier:.*property.*",
    "devices.types.humidifier:.*property.*",
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    prefix = f"{entry.entry_id} - async_setup_entry {PLATFORM}: "
    _LOGGER.debug(
        "Setting up %s platform entry: %s | %s", PLATFORM, DOMAIN, entry.entry_id
    )
    entities = []

    try:
        _LOGGER.debug(f"{prefix}Getting cloud devices from data store")
        entry_data = hass.data[DOMAIN][entry.entry_id]
        api_devices = entry_data[CONF_DEVICES]
    except Exception:
        _LOGGER.error(f"{prefix}Getting cloud devices from data store failed")
        return

    for device_cfg in api_devices:
        try:
            device_id = device_cfg.get("device")
            coordinator = entry_data[CONF_COORDINATORS][device_id]

            # Check each capability for sensor types
            for capability in device_cfg.get("capabilities", []):
                capability_key = (
                    f"{device_cfg.get('type', STATE_UNKNOWN)}:"
                    f"{capability.get('type', STATE_UNKNOWN)}:"
                    f"{capability.get('instance', STATE_UNKNOWN)}"
                )

                # Check if this capability matches any sensor patterns
                if any(
                    re.match(pattern, capability_key)
                    for pattern in PLATFORM_DEVICE_TYPES
                ):
                    _LOGGER.debug(
                        f"{prefix}Setup capability: {device_id}|"
                        f"{capability.get('type', STATE_UNKNOWN).split('.')[-1]}|"
                        f"{capability.get('instance', STATE_UNKNOWN)}"
                    )
                    entity = GoveeLifeSensor(
                        hass,
                        entry,
                        coordinator,
                        device_cfg,
                        capability,
                        platform=PLATFORM,
                    )
                    entities.append(entity)

            await asyncio.sleep(0)
        except Exception:
            _LOGGER.error(f"{prefix}Setup device failed", exc_info=True)
            continue

    _LOGGER.info(f"{prefix}setup {len(entities)} {PLATFORM} entities")
    if entities:
        async_add_entities(entities)


class GoveeLifeSensor(SensorEntity, GoveeLifePlatformEntity, GoveeApiMixin):
    """Sensor class for Govee Life integration."""

    def __init__(self, hass, entry, coordinator, device_cfg, cap, **kwargs):
        """Initialize the sensor."""
        self._cap = cap
        super().__init__(hass, entry, coordinator, device_cfg, **kwargs)
        self._attr_state_class = self._determine_state_class()
        self._attr_native_unit_of_measurement = self._determine_unit()

    def _init_platform_specific(self, **kwargs):
        """Platform specific init actions."""
        # Update entity name and ID with capability instance
        if self._cap and (instance := self._cap.get("instance", "")):
            self._name = f"{self._name} {instance.replace('_', ' ').title()}"
            self._entity_id = f"{self._entity_id}_{instance}"
            self._attr_unique_id = f"{self._identifier}_{self._entity_id}"

    def _determine_state_class(self) -> SensorStateClass | None:
        """Determine the state class based on sensor type."""
        instance = self._cap.get("instance", "").lower()

        # Measurement sensors (values that accumulate or vary over time)
        measurement_patterns = [
            "temperature",
            "humidity",
            "pm",
            "aqi",
            "tvoc",
            "hcho",
            "current",
            "voltage",
            "power",
            "energy",
            "battery",
        ]
        if any(pattern in instance for pattern in measurement_patterns):
            return SensorStateClass.MEASUREMENT

        # Total increasing sensors (cumulative values)
        total_patterns = ["total", "runtime", "filter_life"]
        if any(pattern in instance for pattern in total_patterns):
            return SensorStateClass.TOTAL_INCREASING

        return None

    def _determine_unit(self) -> str | None:
        """Determine the unit of measurement based on sensor type."""
        instance = self._cap.get("instance", "").lower()

        # Temperature units
        if "temperature" in instance:
            # Check if device provides unit info
            if hasattr(self, "_device_cfg"):
                for cap in self._device_cfg.get("capabilities", []):
                    if cap.get("instance") == self._cap.get("instance"):
                        params = cap.get("parameters", {})
                        if "unit" in params:
                            return params["unit"]
            return "°C"  # Default to Celsius

        # Other common units
        unit_mapping = {
            "humidity": "%",
            "battery": "%",
            "pm1": "µg/m³",
            "pm25": "µg/m³",
            "pm10": "µg/m³",
            "tvoc": "ppb",
            "hcho": "mg/m³",
            "voltage": "V",
            "current": "A",
            "power": "W",
            "energy": "kWh",
            "filter_life": "%",
        }

        for key, unit in unit_mapping.items():
            if key in instance:
                return unit

        return None

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Get capability type from string
        cap_type_str = self._cap.get("type", "")
        try:
            cap_type = CapabilityType(cap_type_str)
        except ValueError:
            _LOGGER.warning(f"{self.log_prefix}Unknown capability type: {cap_type_str}")
            return None

        # Get the cached value
        value = self._get_cached_value(cap_type, self._cap.get("instance", ""))

        # Handle different value types
        if value is None:
            return None

        # If it's a dict, try to extract the actual value
        if isinstance(value, dict):
            # Look for common value keys
            for key in ["value", "currentValue", "current", "val"]:
                if key in value:
                    return value[key]
            # If no standard key, log and return the dict as string
            _LOGGER.debug(f"{self.log_prefix}Unexpected value structure: {value}")
            return str(value)

        return value

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Entity is available if we have any cached value
        return self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        attributes = {}

        # Add capability info
        if self._cap:
            attributes["capability_type"] = self._cap.get("type", "unknown")
            attributes["capability_instance"] = self._cap.get("instance", "unknown")

        # Add any additional capability parameters
        cap_type_str = self._cap.get("type", "")
        try:
            cap_type = CapabilityType(cap_type_str)
            value = self._get_cached_value(cap_type, self._cap.get("instance", ""))

            # If value is a dict with extra info, add it to attributes
            if isinstance(value, dict):
                for key, val in value.items():
                    if key not in ["value", "currentValue", "current", "val"]:
                        attributes[key] = val
        except ValueError:
            pass

        return attributes if attributes else None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
