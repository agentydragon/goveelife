"""Config flow for Govee Life."""

from __future__ import annotations

import logging
from typing import Any, Dict, Final, Optional

from homeassistant import config_entries
from homeassistant.const import CONF_FRIENDLY_NAME, CONF_RESOURCE
from homeassistant.core import callback

from .configuration_schema import GOVEELIFE_SCHEMA, async_get_OPTIONS_GOVEELIFE_SCHEMA
from .const import DEFAULT_NAME, DOMAIN

_LOGGER: Final = logging.getLogger(__name__)


class ConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Govee Life."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    data: Optional[Dict[str, Any]] = None

    @property
    def log_prefix(self) -> str:
        """Return logging prefix."""
        return f"{DOMAIN} - ConfigFlowHandler: "

    def __init__(self):
        """Initialize the config flow handler."""
        _LOGGER.debug(f"{self.log_prefix}__init__")

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle a flow initialized by the user."""
        _LOGGER.debug(f"{self.log_prefix}async_step_user: {user_input}")
        try:
            # Removed redundant initialization
            return await self.async_step_resource()
        except Exception:
            _LOGGER.error(f"{self.log_prefix}async_step_user failed")
            return self.async_abort(reason="exception")

    async def async_step_resource(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle resource step in config flow."""
        log_prefix = f"{self.log_prefix}async_step_resource: "
        _LOGGER.debug(f"{log_prefix}{user_input = }")
        try:
            errors: Dict[str, str] = {}
            if user_input is not None:
                _LOGGER.debug(f"{log_prefix}add user_input to data")
                self.data = user_input
                return await self.async_step_final()
            return self.async_show_form(
                step_id=CONF_RESOURCE, data_schema=GOVEELIFE_SCHEMA, errors=errors
            )
            # via the "step_id" the function calls itself after GUI completion
        except Exception:
            _LOGGER.error(f"{log_prefix}failed")
            return self.async_abort(reason="exception")

    async def async_step_final(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle final step in config flow."""
        _LOGGER.debug(f"{self.log_prefix}async_step_final: {user_input}")
        title = self.data.get(CONF_FRIENDLY_NAME, DEFAULT_NAME)
        return self.async_create_entry(title=title, data=self.data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow handler."""
        _LOGGER.debug("%s: ConfigFlowHandler - async_get_options_flow", DOMAIN)
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Govee Life."""

    @property
    def log_prefix(self) -> str:
        """Return logging prefix."""
        return f"{DOMAIN} - OptionsFlowHandler: "

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow handler."""
        _LOGGER.debug(f"{self.log_prefix}__init__: {config_entry}")
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Manage the options for Govee Life."""
        log_prefix = f"{self.log_prefix}async_step_init: "
        _LOGGER.debug(f"{log_prefix}{user_input}")
        try:
            if not hasattr(self, "data"):
                self.data = {}
            if self.config_entry.source != config_entries.SOURCE_USER:
                _LOGGER.warning(
                    f"{log_prefix}source unsupported: {self.config_entry.source}"
                )
                return self.async_abort(reason="not_supported")
            return await self.async_step_config_resource()
        except Exception:
            _LOGGER.error(f"{log_prefix}failed")
            return self.async_abort(reason="exception")

    async def async_step_config_resource(
        self, user_input: Optional[Dict[str, Any]] = None
    ):
        """Handle resource configuration step in options flow."""
        log_prefix = f"{self.log_prefix}async_step_config_resource: "
        _LOGGER.debug(f"{log_prefix}{user_input}")
        try:
            OPTIONS_GOVEELIFE_SCHEMA = await async_get_OPTIONS_GOVEELIFE_SCHEMA(
                self.config_entry.data
            )
            if not user_input:
                return self.async_show_form(
                    step_id="config_resource", data_schema=OPTIONS_GOVEELIFE_SCHEMA
                )
            _LOGGER.debug(f"{log_prefix}{user_input = }")
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input, options=self.config_entry.options
            )
            _LOGGER.debug(f"{log_prefix}complete: {user_input}")
            return await self.async_step_final()
        except Exception:
            _LOGGER.error(f"{log_prefix}failed")
            return self.async_abort(reason="exception")

    async def async_step_final(self):
        """Handle final step in options flow."""
        try:
            _LOGGER.debug(f"{self.log_prefix}async_step_final")
            return self.async_create_entry(title="", data={})
            # title=self.data.get(CONF_FRIENDLY_NAME, DEFAULT_NAME)
            # return self.async_create_entry(title=title, data=self.data)
        except Exception:
            _LOGGER.error(f"{self.log_prefix}async_step_final failed")
            return self.async_abort(reason="exception")
