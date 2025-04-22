from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .coordinator import TelegramCoordinator
from .auto_responder import TelegramAutoResponder
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Telegram Auto Responder from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    if entry.entry_id in hass.data[DOMAIN]:
        return False
  
    # Create a coordinator
    coordinator = TelegramCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Create and save an instance
    responder = TelegramAutoResponder(hass=hass, entry_data=entry.data, config_entry=entry)

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["switch"])
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms(entry, ["switch"])
    hass.data[DOMAIN].pop(entry.entry_id)
    return True

