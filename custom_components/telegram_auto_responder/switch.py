from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .auto_responder import TelegramAutoResponder

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Telegram Auto Responder switch."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TelegramAutoResponderSwitch(coordinator, entry)])

class TelegramAutoResponderSwitch(CoordinatorEntity, RestoreEntity, SwitchEntity):
    """Representation of a Telegram Auto Responder switch."""

    _attr_has_entity_name = True
    translation_key = "telegram_auto_responder"

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Auto Responder"
        self._attr_unique_id = f"{entry.entry_id}_auto_responder_switch"
        self._auto_responder = None
        self._attr_is_on = False
        self._restored = False
        self._attr_extra_state_attributes = self._build_attributes()

    def _build_attributes(self) -> dict:
        """Build the attributes dictionary."""
        ignored_users = self._entry.data.get("ignored_users")
        ignored_users_display = "no" if not ignored_users else ignored_users

        return {
            "phone_number": self._entry.data.get("phone", ""),
            "response_text": self._entry.data.get("response_text", "")[:255],
            "cooldown_minutes": self._entry.data.get("cooldown", 5),
            "max_messages": self._entry.data.get("max_msgs", 1),
            "ignored_users": ignored_users_display,
            "allow_group_chats": self._entry.data.get("allow_group_chats", False),
            "allow_channels": self._entry.data.get("allow_channels", False),
            "allow_bots": self._entry.data.get("allow_bots", False)
        }

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Telegram {self._entry.data.get('phone', '')}",
            "manufacturer": "Telegram",
            "model": "Auto Responder",
            "sw_version": "1.5.2"
        }

    async def async_added_to_hass(self) -> None:
        """Called when an entity is added to HA."""
        await super().async_added_to_hass()
        
        # Restore the previous state
        try:
            if (last_state := await self.async_get_last_state()) is not None:
                self._attr_is_on = last_state.state == "on"
                self._restored = True
                _LOGGER.debug(f"Restored state: {self._attr_is_on} from last_state")
            elif (last_switch_data := await self.async_get_last_switch_data()) is not None:
                self._attr_is_on = last_switch_data.is_on
                self._restored = True
                _LOGGER.debug(f"Restored state: {self._attr_is_on} from last_switch_data")
            else:
                # If there is no saved state, use the value from the coordinator
                self._attr_is_on = getattr(self.coordinator, 'auto_responder_enabled', False)
                _LOGGER.debug(f"No saved state, using coordinator state: {self._attr_is_on}")
        except Exception as e:
            _LOGGER.error(f"Error restoring state: {e}")
            self._attr_is_on = False
        
        self._auto_responder = TelegramAutoResponder(self.hass, self._entry.data)
        
        # Subscribe to updates from the coordinator
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update))
        
        # We start or stop the answering machine depending on the state
        try:
            if self._attr_is_on:
                await self._auto_responder.start()
                _LOGGER.debug("Auto responder started on restore")
            else:
                await self._auto_responder.stop()
                _LOGGER.debug("Auto responder stopped on restore")
        except Exception as e:
            _LOGGER.error(f"Error starting/stopping auto responder: {e}")
            
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self._restored:
            new_state = getattr(self.coordinator, 'auto_responder_enabled', False)
            if new_state != self._attr_is_on:
                self._attr_is_on = new_state
                self.async_write_ha_state()
                _LOGGER.debug(f"State updated from coordinator: {self._attr_is_on}")

    async def async_will_remove_from_hass(self) -> None:
        """Called when an entity is removed from HA."""
        try:
            if self._auto_responder:
                await self._auto_responder.stop()
        except Exception as e:
            _LOGGER.error(f"Error stopping auto responder: {e}")
        await super().async_will_remove_from_hass()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turning on the auto responder."""
        try:
            await self.coordinator.async_set_auto_responder(True)
            if self._auto_responder:
                await self._auto_responder.start()
            self._attr_is_on = True
            self._restored = False  # After manual change, we don't want to restore
            self.async_write_ha_state()
            _LOGGER.debug("Switch turned on")
        except Exception as e:
            _LOGGER.error(f"Error turning on switch: {e}")
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turning off the auto responder."""
        try:
            await self.coordinator.async_set_auto_responder(False)
            if self._auto_responder:
                await self._auto_responder.stop()
            self._attr_is_on = False
            self._restored = False  # After manual change, we don't want to restore
            self.async_write_ha_state()
            _LOGGER.debug("Switch turned off")
        except Exception as e:
            _LOGGER.error(f"Error turning off switch: {e}")
            raise