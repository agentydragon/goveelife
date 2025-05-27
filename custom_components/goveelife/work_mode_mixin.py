"""Work mode handling mixin for Govee Life entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON


_LOGGER = logging.getLogger(__name__)


class WorkModeMixin:
    """Mixin for entities that support work modes."""

    # These should be defined by the entity class
    _attr_preset_modes_mapping: dict[str, int]
    _attr_preset_modes_mapping_set: dict[str, dict[str, int]]
    _attr_available_modes: list[str]
    log_prefix: str

    def init_work_mode_mappings(self) -> None:
        """Initialize work mode related mappings."""
        self._attr_preset_modes_mapping = {}
        self._attr_preset_modes_mapping_set = {}
        self._attr_available_modes = []

    def process_work_mode_capability(self, cap: dict[str, Any]) -> None:
        """Process work mode capability."""
        for field in cap.get("parameters", {}).get("fields", []):
            if field.get("fieldName") == "workMode":
                self._process_work_mode_field(field)
            elif field.get("fieldName") == "modeValue":
                self._process_mode_value_field(field)

    def _process_work_mode_field(self, field: dict[str, Any]) -> None:
        """Process workMode field."""
        for work_option in field.get("options", []):
            name = work_option.get("name", "")
            value = work_option.get("value")
            if name and value is not None:
                self._attr_preset_modes_mapping[name] = value

    def _process_mode_value_field(self, field: dict[str, Any]) -> None:
        """Process modeValue field."""
        for mode_value_option in field.get("options", []):
            if "options" in mode_value_option:
                self._process_parent_mode_with_children(mode_value_option)
            elif mode_value_option.get("name") != "Custom":
                self._process_standalone_mode(mode_value_option)

    def _process_parent_mode_with_children(
        self, mode_value_option: dict[str, Any]
    ) -> None:
        """Process a parent mode that has child options."""
        parent_mode_name = mode_value_option.get("name", "")

        if parent_mode_name not in self._attr_preset_modes_mapping:
            _LOGGER.warning(
                f"{self.log_prefix}Parent mode '{parent_mode_name}' not in work mode mapping"
            )
            return

        parent_work_mode = self._attr_preset_modes_mapping[parent_mode_name]

        for child_option in mode_value_option.get("options", []):
            child_name = child_option.get("name", "")
            child_value = child_option.get("value")

            if child_name and child_value is not None:
                self._attr_available_modes.append(child_name)
                self._attr_preset_modes_mapping_set[child_name] = {
                    "workMode": parent_work_mode,
                    "modeValue": child_value,
                }
                _LOGGER.debug(
                    f"{self.log_prefix}Adding preset mode '{child_name}': "
                    f"workMode={parent_work_mode}, modeValue={child_value}"
                )

    def _process_standalone_mode(self, mode_value_option: dict[str, Any]) -> None:
        """Process a standalone mode without child options."""
        mode_name = mode_value_option.get("name", "")

        if mode_name not in self._attr_preset_modes_mapping:
            _LOGGER.warning(
                f"{self.log_prefix}Mode '{mode_name}' not in work mode mapping"
            )
            return

        self._attr_available_modes.append(mode_name)
        mode_value = self._extract_mode_value(mode_value_option)

        self._attr_preset_modes_mapping_set[mode_name] = {
            "workMode": self._attr_preset_modes_mapping[mode_name],
            "modeValue": mode_value,
        }

    def _extract_mode_value(self, mode_value_option: dict[str, Any]) -> int:
        """Extract mode value from various option structures."""
        # Direct value
        if "value" in mode_value_option:
            return mode_value_option["value"]

        # Default value
        if "defaultValue" in mode_value_option:
            return mode_value_option["defaultValue"]

        # Range value - use minimum
        if "range" in mode_value_option:
            return mode_value_option["range"].get("min", 0)

        # Fallback
        mode_name = mode_value_option.get("name", "unknown")
        _LOGGER.warning(
            f"{self.log_prefix}No value found for mode '{mode_name}', using 0"
        )
        return 0


class StateMappingMixin:
    """Mixin for common state mapping functionality."""

    _state_mapping: dict[int, str]
    _state_mapping_set: dict[str, int]
    log_prefix: str

    def init_state_mappings(self) -> None:
        """Initialize state mappings."""
        self._state_mapping = {}
        self._state_mapping_set = {}

    def process_on_off_capability(self, cap: dict[str, Any]) -> None:
        """Process on/off capability and set up state mappings."""
        for option in cap.get("parameters", {}).get("options", []):
            option_name = option.get("name", "")
            option_value = option.get("value")

            if option_name == "on" and option_value is not None:
                self._state_mapping[option_value] = STATE_ON
                self._state_mapping_set[STATE_ON] = option_value
            elif option_name == "off" and option_value is not None:
                self._state_mapping[option_value] = STATE_OFF
                self._state_mapping_set[STATE_OFF] = option_value
            else:
                _LOGGER.warning(
                    f"{self.log_prefix}process_on_off_capability: "
                    f"unhandled option: {option}"
                )
