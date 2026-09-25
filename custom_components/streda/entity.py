# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Base entity and expose helpers for Isolectra Streda."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, STREDA_ZIGBEE_MANUFACTURER, signal_device
from .hub import StredaDevice, StredaHub


def device_info(device: StredaDevice) -> DeviceInfo:
    streda = device.manufacturer == STREDA_ZIGBEE_MANUFACTURER
    short_model = device.model.split("-03/")[0]
    return DeviceInfo(
        identifiers={(DOMAIN, device.ieee)},
        name=f"{'Streda' if streda else device.vendor or 'Zigbee'} {short_model} {device.ieee[-4:]}",
        manufacturer=MANUFACTURER if streda else device.vendor,
        model=device.model,
        sw_version=device.software,
        serial_number=device.ieee,
    )


def exposes(device: StredaDevice) -> Iterator[dict[str, Any]]:
    """Top-level exposes of a device."""
    yield from device.exposes


def light_endpoints(device: StredaDevice) -> set[str]:
    return {e.get("endpoint") for e in device.exposes if e.get("type") == "light"}


def is_indicator_led(expose: dict[str, Any]) -> bool:
    """Colour-capable light channels are the snap-ins' status LEDs, not real lights."""
    names = {f.get("name") for f in expose.get("features", [])}
    return bool(names & {"color_temp", "color_hs", "color_xy"})


class StredaEntity(Entity):
    """An entity fed by the state messages of one Streda device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: StredaHub, device: StredaDevice, key: str, name: str | None) -> None:
        self._hub = hub
        self._device = device
        self._attr_unique_id = f"{device.ieee}_{key}"
        self._attr_name = name
        self._attr_device_info = device_info(device)

    @property
    def available(self) -> bool:
        return self._hub.connected and self._device.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device.state:
            self._apply(self._device.state, initial=True)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_device(self._hub.entry_id, self._device.ieee), self._on_message
            )
        )

    @callback
    def _on_message(self, payload: dict[str, Any] | None) -> None:
        # None = availability changed only.
        if payload is not None and not self._apply(payload, initial=False):
            return
        self.async_write_ha_state()

    @callback
    def _apply(self, payload: dict[str, Any], initial: bool) -> bool:
        """Update from a (partial) state message. Return True when the entity state may have changed."""
        raise NotImplementedError
