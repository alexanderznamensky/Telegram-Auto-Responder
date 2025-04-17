from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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

class TelegramAutoResponderSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Telegram Auto Responder switch."""

    _attr_has_entity_name = True
    translation_key = "telegram_auto_responder"

    def __init__(self, coordinator, entry: ConfigEntry):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        # self._attr_name = f"Telegram Auto Responder ({entry.data.get('phone', '')})"
        self._attr_name = f"Auto Responder"
        self._attr_unique_id = f"{entry.entry_id}_auto_responder_switch"
        self._attr_is_on = coordinator.auto_responder_enabled
        self._auto_responder = None
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
            "sw_version": "1.4"
        }

    async def async_added_to_hass(self) -> None:
        """Called when an entity is added to HA."""
        await super().async_added_to_hass()
        self._auto_responder = TelegramAutoResponder(self.hass, self._entry.data)
        # Subscribe to updates from coordinator
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        if self._attr_is_on:
            await self._auto_responder.start()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.auto_responder_enabled
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Called when an entity is removed from HA."""
        if self._auto_responder:
            await self._auto_responder.stop()
        await super().async_will_remove_from_hass()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turning on the auto responder."""
        await self.coordinator.async_set_auto_responder(True)
        if self._auto_responder:
            await self._auto_responder.start()
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turning off the auto responder."""
        await self.coordinator.async_set_auto_responder(False)
        if self._auto_responder:
            await self._auto_responder.stop()
        self._attr_is_on = False
        self.async_write_ha_state()