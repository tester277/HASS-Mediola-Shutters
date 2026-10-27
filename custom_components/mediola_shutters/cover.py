"""Cover platform for Mediola Shutters integration."""
import logging
from typing import Any, Optional

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_ER, DEVICE_TYPE_RT, DEVICE_TYPE_WR, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mediola cover entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for shutter in coordinator.data:
        entities.append(MediolaCover(coordinator, shutter, entry))

    async_add_entities(entities)


class MediolaCover(CoordinatorEntity, CoverEntity):
    """Representation of a Mediola shutter cover."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_has_entity_name = True
    _attr_name = None  # Use device name

    def __init__(self, coordinator, shutter_data, entry):
        """Initialize the cover."""
        super().__init__(coordinator)
        self._shutter_data = shutter_data
        self._entry = entry

        self._sid = shutter_data.get("sid")
        self._adr = shutter_data.get("adr")
        self._device_type = shutter_data.get("type")

        self._attr_unique_id = f"{entry.entry_id}_cover_{self._sid}"

        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
        )

        if self._device_type == DEVICE_TYPE_WR:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION

    @property
    def device_info(self):
        """Return device information about this shutter."""
        manufacturer = self.coordinator.api.get_manufacturer(self._device_type)
        model = f"{self._device_type} Shutter"

        # Look up the gateway device's registry ID for via_device_id
        device_registry = dr.async_get(self.hass)
        gateway_device = device_registry.async_get_device_by_identifier(
            (DOMAIN, self._entry.entry_id),
            self._entry.entry_id
        )
        gateway_id = gateway_device.id if gateway_device else None

        info = {
            "identifiers": {(DOMAIN, f"{self._entry.entry_id}_{self._sid}")},
            "name": f"Shutter {self._sid}",
            "manufacturer": manufacturer,
            "model": model,
        }
        if gateway_id:
            info["via_device_id"] = gateway_id

        return info

    @property
    def current_cover_position(self) -> Optional[int]:
        """Return current position of cover (0=closed, 100=open)."""
        for shutter in self.coordinator.data:
            if shutter.get("sid") == self._sid:
                state = shutter.get("state", "")
                device_type = shutter.get("type")

                # RT: use pseudo position from coordinator memory
                if device_type == DEVICE_TYPE_RT:
                    mediola_pos = self.coordinator.rt_positions.get(self._sid)
                    if mediola_pos is None:
                        return None
                    return 100 - mediola_pos  # Invert: Mediola 0=open → HA 100

                position = self.coordinator.api.parse_position(device_type, state)
                if position is None:
                    return None
                ha_position = 100 - position
                return ha_position
        return None

    @property
    def is_closed(self) -> Optional[bool]:
        """Return if the cover is closed."""
        position = self.current_cover_position
        if position is None:
            return None
        return position == 0

    @property
    def is_opening(self) -> Optional[bool]:
        """Return if the cover is opening."""
        if self._device_type == DEVICE_TYPE_ER:
            for shutter in self.coordinator.data:
                if shutter.get("sid") == self._sid:
                    state = shutter.get("state", "")
                    return state == "100A"  # ELERO_STATE_MOVING_UP
        return None

    @property
    def is_closing(self) -> Optional[bool]:
        """Return if the cover is closing."""
        if self._device_type == DEVICE_TYPE_ER:
            for shutter in self.coordinator.data:
                if shutter.get("sid") == self._sid:
                    state = shutter.get("state", "")
                    return state == "100B"  # ELERO_STATE_MOVING_DOWN
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.open_shutter, self._device_type, self._sid, self._adr
        )
        if self._device_type == DEVICE_TYPE_RT:
            self.coordinator.rt_positions[self._sid] = 0  # Mediola 0 = fully open
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.close_shutter, self._device_type, self._sid, self._adr
        )
        if self._device_type == DEVICE_TYPE_RT:
            self.coordinator.rt_positions[self._sid] = 100  # Mediola 100 = fully closed
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.stop_shutter, self._device_type, self._sid, self._adr
        )
        if self._device_type == DEVICE_TYPE_RT:
            self.coordinator.rt_positions[self._sid] = 50  # Assume 50% after stop
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position (WIR only)."""
        if self._device_type != DEVICE_TYPE_WR:
            _LOGGER.warning(
                "Shutter %s (type %s) does not support position setting",
                self._sid,
                self._device_type,
            )
            return

        ha_position = kwargs[ATTR_POSITION]
        mediola_position = 100 - ha_position

        await self.hass.async_add_executor_job(
            self.coordinator.api.set_shutter_position,
            self._device_type,
            self._sid,
            self._adr,
            mediola_position,
        )
        await self.coordinator.async_request_refresh()
