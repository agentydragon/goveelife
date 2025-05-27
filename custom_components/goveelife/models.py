"""Pydantic models for Govee API requests and responses."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

_LOGGER = logging.getLogger(__name__)


class CapabilityType(str, Enum):
    """Capability types supported by Govee API."""

    ON_OFF = "devices.capabilities.on_off"
    WORK_MODE = "devices.capabilities.work_mode"
    RANGE = "devices.capabilities.range"
    COLOR_SETTING = "devices.capabilities.color_setting"
    SEGMENT_COLOR_SETTING = "devices.capabilities.segment_color_setting"
    TOGGLE = "devices.capabilities.toggle"
    MUSIC_SETTING = "devices.capabilities.music_setting"
    DIY_SETTING = "devices.capabilities.diy_setting"
    TEMPERATURE_SETTING = "devices.capabilities.temperature_setting"
    PROPERTY = "devices.capabilities.property"


class CapabilityInstance(str, Enum):
    """Common capability instances."""

    POWER_SWITCH = "powerSwitch"
    WORK_MODE = "workMode"
    BRIGHTNESS = "brightness"
    COLOR = "color"
    COLOR_TEMPERATURE = "colorTemperature"
    HUMIDITY = "humidity"
    TEMPERATURE = "temperature"
    FAN_SPEED = "fanSpeed"
    NIGHT_LIGHT = "nightLight"
    GRADIENT_TOGGLE = "gradientToggle"
    SCENE_MODE = "sceneMode"


# Request Models
class WorkModeValue(BaseModel):
    """Work mode value for capabilities."""

    work_mode: int = Field(alias="workMode")
    mode_value: Optional[int] = Field(alias="modeValue", default=None)


class ColorValue(BaseModel):
    """Color value for capabilities."""

    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


class Capability(BaseModel):
    """Capability in a device control request."""

    type: CapabilityType
    instance: str  # Keep as str since instances can vary
    value: Any  # Can be int, float, dict, etc.


class DeviceControlPayload(BaseModel):
    """Payload for device control request."""

    sku: str
    device: str
    capability: Capability


class DeviceControlRequest(BaseModel):
    """Device control request."""

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), alias="requestId"
    )
    payload: DeviceControlPayload


class DeviceStatePayload(BaseModel):
    """Payload for device state request."""

    sku: str
    device: str


class DeviceStateRequest(BaseModel):
    """Device state request."""

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), alias="requestId"
    )
    payload: DeviceStatePayload


# Response Models
class CapabilityState(BaseModel):
    """State information for a capability."""

    status: Optional[str] = None
    error_code: Optional[int] = Field(alias="errorCode", default=None)
    error_msg: Optional[str] = Field(alias="errorMsg", default=None)
    value: Optional[Any] = None


class CapabilityResponse(BaseModel):
    """Capability in a response."""

    type: CapabilityType
    instance: str
    state: Optional[CapabilityState] = None
    value: Optional[Any] = None  # Some responses have value at this level


class DeviceControlResponse(BaseModel):
    """Response from device control."""

    request_id: str = Field(alias="requestId")
    msg: str
    code: int
    capability: Optional[CapabilityResponse] = None


class DeviceStateCapability(BaseModel):
    """Capability in device state response."""

    type: CapabilityType
    instance: str
    state: dict[str, Any]  # Various state values

    def get_value(self) -> Any:
        """Get the value from state, handling different formats."""
        if not self.state:
            return None
        return self.state.get("value")

    def get_work_mode(self) -> Optional[WorkModeValue]:
        """Get work mode if this is a work_mode capability."""
        if self.type != CapabilityType.WORK_MODE:
            _LOGGER.warning(
                f"get_work_mode called on non-work_mode capability: {self.type}"
            )
            return None

        value = self.get_value()
        if not isinstance(value, dict):
            return None

        work_mode = value.get("workMode")
        mode_value = value.get("modeValue")

        if work_mode is None:
            return None

        return WorkModeValue(work_mode=work_mode, mode_value=mode_value)


class DeviceStateResponse(BaseModel):
    """Response from device state query."""

    capabilities: list[DeviceStateCapability]

    def get_capability(
        self, cap_type: CapabilityType, instance: str
    ) -> Optional[DeviceStateCapability]:
        """Find a specific capability by type and instance."""
        for cap in self.capabilities:
            if (cap.type, cap.instance) == (cap_type, instance):
                return cap
        return None

    def get_capability_value(self, cap_type: CapabilityType, instance: str) -> Any:
        """Get value for a specific capability."""
        cap = self.get_capability(cap_type, instance)
        return cap.get_value() if cap else None


# Device Models
class CapabilityOption(BaseModel):
    """Option for a capability parameter."""

    name: str
    value: Optional[int] = None
    default_value: Optional[int] = Field(alias="defaultValue", default=None)
    range: Optional[dict[str, int]] = None
    options: Optional[list[CapabilityOption]] = None


class CapabilityField(BaseModel):
    """Field in capability parameters."""

    field_name: str = Field(alias="fieldName")
    data_type: str = Field(alias="dataType")
    options: Optional[list[CapabilityOption]] = None
    required: Optional[bool] = None
    size: Optional[dict[str, int]] = None
    element_type: Optional[str] = Field(alias="elementType", default=None)
    element_range: Optional[dict[str, int]] = Field(alias="elementRange", default=None)


class CapabilityParameters(BaseModel):
    """Parameters for a capability."""

    data_type: Optional[str] = Field(alias="dataType", default=None)
    fields: Optional[list[CapabilityField]] = None
    options: Optional[list[CapabilityOption]] = None
    range: Optional[dict[str, int]] = None


class DeviceCapability(BaseModel):
    """Device capability definition."""

    type: CapabilityType
    instance: str
    parameters: CapabilityParameters


class Device(BaseModel):
    """Device information."""

    sku: str
    device: str
    device_name: str = Field(alias="deviceName")
    spec: Optional[str] = None
    version: Optional[str] = None
    type: str
    capabilities: list[DeviceCapability]


class DevicesResponse(BaseModel):
    """Response from devices list."""

    code: int
    message: str
    devices: list[Device]


# Helper functions
def create_work_mode_capability(
    work_mode: int, mode_value: Optional[int] = None
) -> Capability:
    """Create a work mode capability."""
    value = WorkModeValue(work_mode=work_mode, mode_value=mode_value)

    return Capability(
        type=CapabilityType.WORK_MODE,
        instance=CapabilityInstance.WORK_MODE,
        value=value.model_dump(by_alias=True, exclude_none=True),
    )


def create_on_off_capability(value: int) -> Capability:
    """Create an on/off capability."""
    return Capability(
        type=CapabilityType.ON_OFF,
        instance=CapabilityInstance.POWER_SWITCH,
        value=value,
    )


def create_range_capability(instance: str, value: float | int) -> Capability:
    """Create a range capability."""
    return Capability(type=CapabilityType.RANGE, instance=instance, value=value)


# Convenience functions for specific capabilities
def brightness_range(value: int) -> Capability:
    """Create a brightness range capability."""
    return create_range_capability("brightness", value)


def color_rgb(value: int) -> Capability:
    """Create a color RGB capability."""
    return Capability(
        type=CapabilityType.COLOR_SETTING,
        instance="colorRgb",
        value=value,
    )


def color_temperature(value: int) -> Capability:
    """Create a color temperature capability."""
    return Capability(
        type=CapabilityType.COLOR_SETTING,
        instance="colorTemperatureK",
        value=value,
    )


def temperature_setting(instance: str, temperature: float, unit: str) -> Capability:
    """Create a temperature setting capability."""
    return Capability(
        type=CapabilityType.TEMPERATURE_SETTING,
        instance=instance,
        value={"temperature": temperature, "unit": unit},
    )
