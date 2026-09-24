"""Dimmers of Streda snap-ins (e.g. SN2-E). The colour-capable status LEDs are not exposed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import StredaConfigEntry
from .entity import StredaEntity, is_indicator_led
from .hub import StredaDevice, StredaHub


async def async_setup_entry(
    hass: HomeAssistant, entry: StredaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    async_add_entities(
        StredaDimmer(hub, device, e["endpoint"], {f["name"] for f in e["features"]})
        for device in hub.devices.values()
        for e in device.exposes
        if e.get("type") == "light" and e.get("endpoint") and not is_indicator_led(e)
    )


class StredaDimmer(StredaEntity, LightEntity):
    """A dimmable light channel (`state_lX` / `brightness_lX`)."""

    def __init__(self, hub: StredaHub, device: StredaDevice, endpoint: str, features: set[str]) -> None:
        super().__init__(hub, device, endpoint, f"Dimmer {endpoint}")
        self._ep = endpoint
        dimmable = "brightness" in features
        self._attr_color_mode = ColorMode.BRIGHTNESS if dimmable else ColorMode.ONOFF
        self._attr_supported_color_modes = {self._attr_color_mode}

    @callback
    def _apply(self, payload: dict[str, Any], initial: bool) -> bool:
        changed = False
        if (state := payload.get(f"state_{self._ep}")) in ("ON", "OFF"):
            self._attr_is_on = state == "ON"
            changed = True
        brightness = payload.get(f"brightness_{self._ep}")
        if isinstance(brightness, (int, float)):
            if brightness > 0:
                self._attr_brightness = int(brightness)
                # The dimmer reports a new level when it is switched on from its wall button.
                if not isinstance(state, str):
                    self._attr_is_on = True
            changed = True
        return changed

    async def async_turn_on(self, **kwargs: Any) -> None:
        payload: dict[str, Any] = {f"state_{self._ep}": "ON"}
        if ATTR_BRIGHTNESS in kwargs:
            payload[f"brightness_{self._ep}"] = kwargs[ATTR_BRIGHTNESS]
        await self._hub.async_command(self._device, payload)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hub.async_command(self._device, {f"state_{self._ep}": "OFF"})
