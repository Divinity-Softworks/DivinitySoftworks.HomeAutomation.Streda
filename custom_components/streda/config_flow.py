# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Config flow for Isolectra Streda: connect directly to the Streda box's MQTT broker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .client import probe
from .const import CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, DEFAULT_PORT, DOMAIN


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


class StredaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up the connection to a Streda box."""

    VERSION = 2

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
        errors: dict[str, str] = {}
        if user_input is not None:
            data, count, error = await self._validate(user_input)
            await self.async_set_unique_id(f"{data[CONF_HOST]}:{data[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title=f"Streda box {data[CONF_HOST]} ({count} devices)", data=data)

        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
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
