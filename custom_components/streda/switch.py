# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Relay channels of Streda snap-ins.

Relays are switches; a relay that drives a lamp can be shown as a light with Home Assistant's own
"Show as" option on the entity.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import StredaConfigEntry
from .const import FOLLOW_BUTTON
from .entity import StredaEntity, light_endpoints
from .hub import StredaDevice, StredaHub


async def async_setup_entry(
    hass: HomeAssistant, entry: StredaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    entities = []
    for device in hub.devices.values():
        lights = light_endpoints(device)
        for e in device.exposes:
            ep = e.get("endpoint")
            if e.get("type") == "switch" and ep and ep not in lights:
                entities.append(StredaRelay(hub, device, ep, e["features"][0]["property"]))
    async_add_entities(entities)


class StredaRelay(StredaEntity, SwitchEntity):
    """A relay channel (`state_lX`)."""

    def __init__(self, hub: StredaHub, device: StredaDevice, endpoint: str, prop: str) -> None:
        super().__init__(hub, device, endpoint, f"Relay {endpoint}")
        self._prop = prop
        self._button = FOLLOW_BUTTON.get(device.model, {}).get(endpoint)
        if self._button:
            self._attr_extra_state_attributes = {"follows_button": self._button}

    @callback
    def _apply(self, payload: dict[str, Any], initial: bool) -> bool:
        if (state := payload.get(self._prop)) in ("ON", "OFF"):
            self._attr_is_on = state == "ON"
            return True
        # The relay switched locally by its own button, which it does not report itself.
        if self._button and not initial:
            action = payload.get("action")
            if action == f"singleup_{self._button}":
                self._attr_is_on = True
                return True
            if action == f"singledown_{self._button}":
                self._attr_is_on = False
                return True
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._hub.async_command(self._device, {self._prop: "ON"})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hub.async_command(self._device, {self._prop: "OFF"})
