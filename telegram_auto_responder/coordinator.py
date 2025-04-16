from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import logging

_LOGGER = logging.getLogger(__name__)

class TelegramCoordinator(DataUpdateCoordinator):
    """Class to manage Telegram Auto Responder data."""
    
    def __init__(self, hass, entry):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name="Telegram Auto Responder",
            update_interval=None,
        )
        self._entry = entry
        self._auto_responder_enabled = entry.data.get("auto_responder_enabled", False)

    async def _async_update_data(self):
        """Update coordinator data."""
        return {"enabled": self._auto_responder_enabled}

    @property
    def auto_responder_enabled(self):
        """Return current state of auto responder."""
        return self._auto_responder_enabled

    async def async_set_auto_responder(self, enabled: bool):
        """Enable/disable auto responder."""
        self._auto_responder_enabled = enabled
        self.async_update_listeners()
