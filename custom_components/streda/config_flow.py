# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Config flow for Isolectra Streda: connect directly to the Streda box's MQTT broker.

Setup starts with a read-only search of the local network; the user picks a box that was found or
enters the address by hand.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import probe
from .const import CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, DEFAULT_PORT, DOMAIN
from .discovery import FoundBox, async_find_boxes

_LOGGER = logging.getLogger(__name__)

# Choice in the list of found boxes to enter the address by hand instead.
MANUAL = "manual"
FIND_IP_URL = "https://github.com/Divinity-Softworks/DivinitySoftworks.HomeAutomation.Streda#finding-the-ip-address-of-the-box"


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Optional(CONF_USERNAME, description={"suggested_value": defaults.get(CONF_USERNAME)}): str,
            vol.Optional(
                CONF_PASSWORD, description={"suggested_value": defaults.get(CONF_PASSWORD)}
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required(
                CONF_BASE_TOPIC, default=defaults.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
            ): str,
        }
    )


def _title(host: str, count: int) -> str:
    return f"Streda box {host} ({count} devices)"


class StredaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up the connection to a Streda box."""

    VERSION = 2

    def __init__(self) -> None:
        self._scan: asyncio.Task[list[FoundBox]] | None = None
        self._found: list[FoundBox] = []

    async def _validate(self, user_input: dict[str, Any]) -> tuple[dict[str, Any], int | None, str | None]:
        data = {
            CONF_HOST: user_input[CONF_HOST].strip(),
            CONF_PORT: user_input[CONF_PORT],
            CONF_BASE_TOPIC: user_input[CONF_BASE_TOPIC].strip().strip("/"),
        }
        if user_input.get(CONF_USERNAME):
            data[CONF_USERNAME] = user_input[CONF_USERNAME]
            data[CONF_PASSWORD] = user_input.get(CONF_PASSWORD)
        count, error = await self.hass.async_add_executor_job(
            probe,
            data[CONF_HOST],
            data[CONF_PORT],
            data.get(CONF_USERNAME),
            data.get(CONF_PASSWORD),
            data[CONF_BASE_TOPIC],
        )
        return data, count, error

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Search the network for Streda boxes first."""
        if self._scan is None:
            self._scan = self.hass.async_create_task(async_find_boxes(self.hass))
        if not self._scan.done():
            return self.async_show_progress(step_id="user", progress_action="scan", progress_task=self._scan)

        try:
            found = self._scan.result()
        except Exception:  # noqa: BLE001 - the search is a convenience; entering the address still works
            _LOGGER.exception("Searching the network for Streda boxes failed")
            found = []
        configured = {entry.unique_id for entry in self._async_current_entries(include_ignore=False)}
        self._found = [box for box in found if f"{box.host}:{box.port}" not in configured]
        if len(self._found) < len(found):
            _LOGGER.debug("Not offering boxes that are already set up: %s", configured)
        return self.async_show_progress_done(next_step_id="pick" if self._found else "manual")

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose one of the boxes that were found, or enter the address by hand."""
        if user_input is not None:
            box = next((box for box in self._found if box.host == user_input[CONF_HOST]), None)
            if box is None:
                return await self.async_step_manual()
            await self.async_set_unique_id(f"{box.host}:{box.port}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_title(box.host, box.devices),
                data={CONF_HOST: box.host, CONF_PORT: box.port, CONF_BASE_TOPIC: DEFAULT_BASE_TOPIC},
            )

        options = [
            SelectOptionDict(value=box.host, label=f"{box.host} ({box.devices} devices)") for box in self._found
        ]
        options.append(SelectOptionDict(value=MANUAL, label=MANUAL))
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=self._found[0].host): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST, translation_key="box")
                )
            }
        )
        return self.async_show_form(
            step_id="pick", data_schema=schema, description_placeholders={"count": str(len(self._found))}
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Enter the address of the box by hand."""
        errors: dict[str, str] = {}
        # Coming from the list of found boxes, user_input holds only the choice, not this form.
        if user_input is not None and CONF_PORT in user_input:
            data, count, error = await self._validate(user_input)
            await self.async_set_unique_id(f"{data[CONF_HOST]}:{data[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title=_title(data[CONF_HOST], count or 0), data=data)
        else:
            user_input = None

        return self.async_show_form(
            step_id="manual",
            data_schema=_schema(user_input or {}),
            errors=errors,
            description_placeholders={"find_ip_url": FIND_IP_URL},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the address or credentials, e.g. when the Streda box got a new IP address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, _count, error = await self._validate(user_input)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, unique_id=f"{data[CONF_HOST]}:{data[CONF_PORT]}", data=data
                )

        return self.async_show_form(
            step_id="reconfigure", data_schema=_schema(user_input or dict(entry.data)), errors=errors
        )
