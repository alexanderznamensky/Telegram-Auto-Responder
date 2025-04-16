from __future__ import annotations
import logging
from typing import Any, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import STATE_ON

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

class TelegramAutoResponderSwitch(CoordinatorEntity, SwitchEntity, RestoreEntity):
    """Representation of a Telegram Auto Responder switch with state restoration."""

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = f"Telegram Auto Responder ({entry.data.get('phone', '')})"
        self._attr_unique_id = f"{entry.entry_id}_auto_responder_switch"
        self._attr_is_on = False
        self._auto_responder: Optional[TelegramAutoResponder] = None
        self._attr_extra_state_attributes = self._build_attributes()

    def _build_attributes(self) -> dict:
        """Build the attributes dictionary."""
        return {
            "cooldown_minutes": self._entry.data.get("cooldown", 5),
            "max_messages": self._entry.data.get("max_msgs", 1),
            "response_text": self._entry.data.get("response_text", "")[:255],
            "ignored_users": self._entry.data.get("ignored_users", ""),
            "phone_number": self._entry.data.get("phone", ""),
            "allow_group_chats": self._entry.data.get("allow_group_chats", False),
            "allow_channels": self._entry.data.get("allow_channels", False),
            "allow_bots": self._entry.data.get("allow_bots", False)
        }

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass."""
        await super().async_added_to_hass()
        
        # 1. First try to restore state
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_is_on = last_state.state == STATE_ON
        else:
            self._attr_is_on = self.coordinator.auto_responder_enabled

        # 2. Initialize auto responder with the correct state
        self._auto_responder = TelegramAutoResponder(self.hass, self._entry.data)
        
        # 3. Sync with coordinator
        await self.coordinator.async_set_auto_responder(self._attr_is_on)
        
        # 4. Start/stop based on final state
        if self._attr_is_on:
            await self._auto_responder.start()
        else:
            await self._auto_responder.stop()

        # 5. Setup coordinator listener
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

        # 6. Write state to HA
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Only update if coordinator has a different state
        if self._attr_is_on != self.coordinator.auto_responder_enabled:
            self._attr_is_on = self.coordinator.auto_responder_enabled
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the auto responder."""
        self._attr_is_on = True
        await self.coordinator.async_set_auto_responder(True)
        if self._auto_responder:
            await self._auto_responder.start()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the auto responder."""
        self._attr_is_on = False
        await self.coordinator.async_set_auto_responder(False)
        if self._auto_responder:
            await self._auto_responder.stop()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Called when entity is about to be removed from hass."""
        if self._auto_responder:
            await self._auto_responder.stop()
        await super().async_will_remove_from_hass()