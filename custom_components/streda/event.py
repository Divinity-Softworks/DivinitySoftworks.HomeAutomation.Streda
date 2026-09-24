"""Button presses of Streda wall switches, and the doorbell."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import StredaConfigEntry
from .const import DOORBELL_INPUT, EVENT_TYPES, FOLLOW_BUTTON
from .entity import StredaEntity
from .hub import StredaDevice, StredaHub


async def async_setup_entry(
    hass: HomeAssistant, entry: StredaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    entities: list[EventEntity] = []
    for device in hub.devices.values():
        if any(e.get("name") == "action" for e in device.exposes):
            entities.append(StredaButton(hub, device))
        if doorbell := DOORBELL_INPUT.get(device.model):
            entities.append(StredaDoorbell(hub, device, doorbell))
    async_add_entities(entities)


class StredaButton(StredaEntity, EventEntity):
    """Button presses, e.g. `singleup_l3` -> event type `singleup` with channel `l3`.

    Only wall switches (battery units and the wired door units) really press buttons; on other snap-ins
    the entity is disabled by default.
    """

    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = EVENT_TYPES

    def __init__(self, hub: StredaHub, device: StredaDevice) -> None:
        super().__init__(hub, device, "action", "Button")
        self._attr_entity_registry_enabled_default = (
            device.battery_powered or device.model in FOLLOW_BUTTON
        )

    @callback
    def _apply(self, payload: dict[str, Any], initial: bool) -> bool:
        action = payload.get("action")
        if initial or not isinstance(action, str) or not action:
            return False
        press, _, channel = action.rpartition("_")
        if not press:  # no channel suffix
            press, channel = action, ""
        event_type = press if press in EVENT_TYPES else "other"
        self._trigger_event(event_type, {"action": action, "channel": channel})
        return True


class StredaDoorbell(StredaEntity, EventEntity):
    """Doorbell push wired to an input of a wall unit."""

    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types = ["ring"]

    def __init__(self, hub: StredaHub, device: StredaDevice, channel: str) -> None:
        super().__init__(hub, device, f"doorbell_{channel}", "Doorbell")
        self._action = f"singleup_{channel}"

    @callback
    def _apply(self, payload: dict[str, Any], initial: bool) -> bool:
        if initial or payload.get("action") != self._action:
            return False
        self._trigger_event("ring")
        return True
