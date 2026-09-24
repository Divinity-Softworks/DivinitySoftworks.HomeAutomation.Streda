"""Binary sensors: smoke, fault and battery low."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import StredaConfigEntry
from .entity import StredaEntity
from .hub import StredaDevice, StredaHub


async def async_setup_entry(
    hass: HomeAssistant, entry: StredaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for device in hub.devices.values():
        names = {e.get("name") for e in device.exposes}
        if "smoke" in names:
            entities.append(
                StredaBinary(hub, device, "smoke", "Smoke", ("smoke",), BinarySensorDeviceClass.SMOKE)
            )
        if "fault" in names:
            entities.append(
                StredaBinary(
                    hub, device, "fault", "Fault", ("fault",), BinarySensorDeviceClass.PROBLEM,
                    EntityCategory.DIAGNOSTIC,
                )
            )
        if "battery_low" in names:
            # The smoke detectors report `battery_low`, the Streda wall switches `batteryLow`.
            entities.append(StredaBatteryLow(hub, device))
    async_add_entities(entities)


class StredaBinary(StredaEntity, BinarySensorEntity):
    def __init__(
        self,
        hub: StredaHub,
        device: StredaDevice,
        key: str,
        name: str,
        props: tuple[str, ...],
        device_class: BinarySensorDeviceClass,
        category: EntityCategory | None = None,
    ) -> None:
        super().__init__(hub, device, key, name)
        self._props = props
        self._attr_device_class = device_class
        self._attr_entity_category = category

    @callback
    def _apply(self, payload: dict[str, Any], initial: bool) -> bool:
        for prop in self._props:
            if isinstance(value := payload.get(prop), bool):
                self._attr_is_on = value
                return True
        return False


class StredaBatteryLow(StredaBinary, RestoreEntity):
    """Battery low flag; restored across restarts because battery devices report rarely."""

    def __init__(self, hub: StredaHub, device: StredaDevice) -> None:
        super().__init__(
            hub, device, "battery_low", "Battery low", ("battery_low", "batteryLow"),
            BinarySensorDeviceClass.BATTERY, EntityCategory.DIAGNOSTIC,
        )

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) is not None and last.state in (STATE_ON, "off"):
            self._attr_is_on = last.state == STATE_ON
        await super().async_added_to_hass()
