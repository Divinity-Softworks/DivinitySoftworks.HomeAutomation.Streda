"""Config flow for Isolectra Streda."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import callback

from .const import CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, DOMAIN

PROBE_TIMEOUT = 10


class StredaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up the Streda integration on top of an MQTT connection to the Streda box."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            return self.async_abort(reason="mqtt_not_connected")

        errors: dict[str, str] = {}
        if user_input is not None:
            base = user_input[CONF_BASE_TOPIC].strip().strip("/")
            await self.async_set_unique_id(base)
            self._abort_if_unique_id_configured()
            count = await self._probe(base)
            if count is None:
                errors["base"] = "no_device_list"
            else:
                return self.async_create_entry(
                    title=f"Streda ({count} devices)", data={CONF_BASE_TOPIC: base}
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): str}
            ),
            errors=errors,
        )

    async def _probe(self, base: str) -> int | None:
        """Read the retained device list once. Returns the number of devices, or None."""
        received: asyncio.Future[int] = self.hass.loop.create_future()

        @callback
        def _msg(msg: mqtt.ReceiveMessage) -> None:
            if received.done():
                return
            try:
                devices = json.loads(msg.payload)
                received.set_result(sum(1 for d in devices if d.get("type") != "Coordinator"))
            except (TypeError, ValueError, AttributeError):
                received.set_result(0)

        unsub = await mqtt.async_subscribe(self.hass, f"{base}/bridge/devices", _msg)
        try:
            return await asyncio.wait_for(received, PROBE_TIMEOUT)
        except TimeoutError:
            return None
        finally:
            unsub()
