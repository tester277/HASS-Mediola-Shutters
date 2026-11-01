"""Config flow for Mediola Shutters integration."""
import logging
from collections.abc import Mapping
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .mediola_api import MediolaAPI, MediolaAuthError

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)

# Schema for user input
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            cv.positive_int, vol.Range(min=5, max=300)
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys host, username and password.
    """
    api = MediolaAPI(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD])

    # Try to connect and get states
    try:
        shutters = await hass.async_add_executor_job(api.get_states)
    except MediolaAuthError as err:
        raise InvalidAuth from err
    except Exception as err:
        _LOGGER.error("Could not connect to Mediola gateway: %s", err)
        raise CannotConnect from err

    # Return info that we want to store in the config entry
    return {
        "title": f"Mediola Gateway ({data[CONF_HOST]})",
        "num_shutters": len(shutters),
    }


class MediolaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mediola Shutters."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create a unique ID based on the host
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Start the reauth flow (credentials rejected by the gateway)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Ask for new credentials."""
        errors: Dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            new_data = {
                **entry.data,
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                await validate_input(self.hass, new_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(entry, data=new_data)

        username = (
            user_input[CONF_USERNAME]
            if user_input is not None
            else entry.data[CONF_USERNAME]
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=username): cv.string,
                    vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                }
            ),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "MediolaOptionsFlowHandler":
        """Get the options flow for this handler."""
        return MediolaOptionsFlowHandler()


class MediolaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Mediola Shutters integration."""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options (host, credentials and scan interval)."""
        errors: Dict[str, str] = {}
        entry = self.config_entry

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            username = user_input[CONF_USERNAME]
            # Empty password field = keep the current password
            password = user_input.get(CONF_PASSWORD) or entry.data[CONF_PASSWORD]
            scan_interval = user_input[CONF_SCAN_INTERVAL]

            host_changed = host != entry.data[CONF_HOST]
            connection_changed = (
                host_changed
                or username != entry.data[CONF_USERNAME]
                or password != entry.data[CONF_PASSWORD]
            )

            # The host is the unique ID: do not allow duplicates
            if host_changed and any(
                other.entry_id != entry.entry_id and other.unique_id == host
                for other in self.hass.config_entries.async_entries(DOMAIN)
            ):
                errors[CONF_HOST] = "already_configured"

            # Only test the connection if host or credentials changed
            if connection_changed and not errors:
                try:
                    await validate_input(
                        self.hass,
                        {
                            CONF_HOST: host,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                        },
                    )
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"

            if not errors:
                options = {CONF_SCAN_INTERVAL: scan_interval}
                if connection_changed:
                    # Host/credentials live in entry.data. Updating data and
                    # options in one call triggers a single reload via the
                    # update listener.
                    extra: Dict[str, Any] = {}
                    if host_changed:
                        extra = {
                            "unique_id": host,
                            "title": f"Mediola Gateway ({host})",
                        }
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            CONF_HOST: host,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                        },
                        options=options,
                        **extra,
                    )
                return self.async_create_entry(title="", data=options)

        # Defaults: entered values (after an error) or the current settings
        if user_input is not None:
            current_host = user_input[CONF_HOST]
            current_username = user_input[CONF_USERNAME]
            current_scan_interval = user_input[CONF_SCAN_INTERVAL]
        else:
            current_host = entry.data[CONF_HOST]
            current_username = entry.data[CONF_USERNAME]
            current_scan_interval = entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )

        options_schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current_host): cv.string,
                vol.Required(CONF_USERNAME, default=current_username): cv.string,
                vol.Optional(CONF_PASSWORD): PASSWORD_SELECTOR,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=current_scan_interval
                ): vol.All(cv.positive_int, vol.Range(min=5, max=300)),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate the gateway rejected the credentials."""
