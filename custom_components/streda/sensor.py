# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Sensors: relay current and estimated power, battery, temperature, link quality."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import StredaConfigEntry
from .const import MAINS_VOLTAGE
from .entity import StredaEntity
from .hub import StredaDevice, StredaHub


async def async_setup_entry(
    hass: HomeAssistant, entry: StredaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    entities: list[SensorEntity] = []
    for device in hub.devices.values():
        for e in device.exposes:
            name, ep = e.get("name"), e.get("endpoint")
            if name == "current" and ep:
                entities.append(StredaCurrent(hub, device, ep, e["property"]))
                entities.append(StredaPower(hub, device, ep, e["property"]))
            elif name == "battery_low":
                # Battery wall switches only advertise battery_low but do report a percentage.
                entities.append(StredaBattery(hub, device))
            elif name == "temperature":
                entities.append(StredaTemperature(hub, device))
            elif name == "linkquality":
                entities.append(StredaLinkQuality(hub, device))
    async_add_entities(entities)


class _NumberSensor(StredaEntity, SensorEntity):
    _prop: str

    @callback
    def _apply(self, payload: dict[str, Any], initial: bool) -> bool:
        value = payload.get(self._prop)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self._attr_native_value = self._convert(value)
            return True
        return False

    def _convert(self, value: float) -> float:
        return value


class StredaCurrent(_NumberSensor):
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub: StredaHub, device: StredaDevice, endpoint: str, prop: str) -> None:
        super().__init__(hub, device, f"current_{endpoint}", f"Relay {endpoint} current")
        self._prop = prop


class StredaPower(_NumberSensor):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, hub: StredaHub, device: StredaDevice, endpoint: str, prop: str) -> None:
        super().__init__(hub, device, f"power_{endpoint}", f"Relay {endpoint} power (est.)")
        self._prop = prop

    def _convert(self, value: float) -> float:
        return round(value * MAINS_VOLTAGE, 1)


class StredaTemperature(_NumberSensor):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _prop = "temperature"

    def __init__(self, hub: StredaHub, device: StredaDevice) -> None:
        super().__init__(hub, device, "temperature", "Temperature")


class StredaLinkQuality(_NumberSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = "lqi"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:signal"
    _prop = "linkquality"

    def __init__(self, hub: StredaHub, device: StredaDevice) -> None:
        super().__init__(hub, device, "linkquality", "Link quality")


class StredaBattery(_NumberSensor, RestoreSensor):
    """Battery level. Battery devices report rarely (mostly when pressed), so the last value is restored."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _prop = "battery"

    def __init__(self, hub: StredaHub, device: StredaDevice) -> None:
        super().__init__(hub, device, "battery", "Battery")

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value
        await super().async_added_to_hass()
