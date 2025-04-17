from __future__ import annotations
import logging
import time
import voluptuous as vol
from typing import Any, Optional
from asyncio import timeout
from telethon.errors.rpcerrorlist import ApiIdInvalidError
from telethon.errors.rpcerrorlist import FloodWaitError
import datetime

from homeassistant.helpers import translation
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    ApiIdInvalidError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
)

from .const import (
    DOMAIN,
    CONF_API_ID,
    CONF_API_HASH,
    CONF_SESSION,
    CONF_PHONE,
    CONF_CODE,
    CONF_PASSWORD,
    CONF_IGNORED_USERS,
    CONF_RESPONSE_TEXT,
    CONF_COOLDOWN,
    CONF_MAX_MSGS,
    CONF_ALLOW_GROUP_CHATS,
    CONF_ALLOW_CHANNELS,
    CONF_ALLOW_BOTS
)

_LOGGER = logging.getLogger(__name__)

AUTH_TIMEOUT = 30  # seconds

class TelegramAuthFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Telegram auth flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize flow."""
        self._client = None
        self._api_id = None
        self._api_hash = None
        self._phone = None
        self._code = None
        self._password = None
        self._request_code_time = None
        self._last_flood_wait = None
        self._session_string = None

    @callback
    def async_abort_by_reason(self, reason, description_placeholders=None):
        """Abort the flow with a specific reason."""
        if reason == "flood_wait":
            return self.async_abort(
                reason=reason,
                description_placeholders=description_placeholders
            )
        return self.async_abort(reason=reason)

    async def _disconnect_client(self):
        """Safely disconnect client if exists."""
        try:
            if self._client and self._client.is_connected():
                await self._client.disconnect()
        except Exception as ex:
            _LOGGER.warning("Error disconnecting client: %s", ex)
        finally:
            self._client = None

    async def _ensure_client(self) -> bool:
        """Ensure Telegram client is connected."""
        try:
            if self._client is None:
                if not self._api_id or not self._api_hash:
                    _LOGGER.error("API credentials not set")
                    return False
                
                self._client = TelegramClient(
                    StringSession(),
                    int(self._api_id),
                    self._api_hash
                )
            
            if not self._client.is_connected():
                await self._client.connect()
                # Verify the connection is actually established
                if not self._client.is_connected():
                    _LOGGER.error("Client connection failed")
                    return False
                
            return True
        except Exception as ex:
            _LOGGER.error("Error ensuring client connection: %s", ex, exc_info=True)
            await self._disconnect_client()
            return False

    async def _save_session(self) -> Optional[str]:
        """Safely save session data with connection check."""
        try:
            if self._client is None:
                _LOGGER.error("Client is None when saving session")
                return None
                
            if not self._client.is_connected():
                _LOGGER.debug("Client disconnected, attempting to reconnect...")
                await self._client.connect()

            if not await self._ensure_client():
                _LOGGER.error("Cannot save session - client not connected")
                return None
                
            if not self._client or not self._client.is_connected():
                _LOGGER.error("Client not connected when saving session")
                return None

            session_string = self._client.session.save()
            if not session_string:
                _LOGGER.error("Empty session string after save")
                return None

            return session_string
        except Exception as ex:
            _LOGGER.error("Session save failed: %s", ex, exc_info=True)
            return None

    async def async_step_user(self, user_input=None):
        """First step - validate API credentials."""
        errors = {}
        
        if user_input is not None:
            try:
                await self._disconnect_client()
                
                try:
                    self._api_id = int(user_input[CONF_API_ID])
                    self._api_hash = user_input[CONF_API_HASH].strip()
                    
                    # Checking the uniqueness of the combination api_id + phone
                    existing_entries = self._async_current_entries()
                    for entry in existing_entries:
                        if (entry.data.get(CONF_API_ID) == self._api_id and 
                            entry.data.get(CONF_API_HASH) == self._api_hash):
                            errors["base"] = "already_configured"
                            break
                    
                    if not errors:
                        self._client = TelegramClient(
                            StringSession(),
                            self._api_id,
                            self._api_hash
                        )
                        try:
                            await self._client.connect()
                            if not await self._client.is_user_authorized():
                                await self._client.disconnect()
                                return await self.async_step_phone()
                        except ApiIdInvalidError:
                            errors["base"] = "invalid_auth"
                        except Exception:
                            errors["base"] = "connection_failed"
                        finally:
                            await self._disconnect_client()
                            
                except ValueError:
                    errors["base"] = "invalid_api_id"
                    
            except Exception as ex:
                errors["base"] = "unknown"
                _LOGGER.exception("Unexpected error: %s", ex)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_ID): cv.string,
                vol.Required(CONF_API_HASH): cv.string
            }),
            errors=errors
        )


    async def async_step_phone(self, user_input=None):
        """Step to enter phone number with flood wait handling."""
        errors = {}
        
        if user_input is not None:
            phone_number = user_input[CONF_PHONE].strip()
            
            if not phone_number.startswith('+'):
                errors["base"] = "invalid_phone_format"
            else:
                self._phone = phone_number
                try:
                    if not await self._ensure_client():
                        errors["base"] = "connection_failed"
                    else:
                        try:
                            await self._client.send_code_request(self._phone)
                            self._request_code_time = time.time()
                            # Return the code entry form directly
                            return self.async_show_form(
                                step_id="code",
                                data_schema=vol.Schema({
                                    vol.Required(CONF_CODE): cv.string
                                }),
                                description_placeholders={
                                    "phone": self._phone
                                }
                            )
                        except FloodWaitError as e:
                            wait_time = str(datetime.timedelta(seconds=e.seconds))
                            return self.async_abort(
                                reason="flood_wait",
                                description_placeholders={"wait_time": wait_time}
                            )
                        except PhoneNumberInvalidError:
                            errors["base"] = "invalid_phone"
                        except Exception as ex:
                            errors["base"] = "send_code_failed"
                            _LOGGER.error("Error sending code: %s", ex)
                except Exception as ex:
                    errors["base"] = "unknown"
                    _LOGGER.error("Unexpected error: %s", ex)

        return self.async_show_form(
            step_id="phone",
            data_schema=vol.Schema({
                vol.Required(CONF_PHONE, default="+"): cv.string
            }),
            errors=errors
        )

    async def async_step_code(self, user_input=None):
        """Step to enter verification code."""
        errors = {}
        
        if user_input is not None:
            self._code = user_input[CONF_CODE].strip()
            try:
                if not await self._ensure_client():
                    errors["base"] = "connection_failed"
                else:
                    try:
                        async with timeout(AUTH_TIMEOUT):
                            await self._client.sign_in(
                                phone=self._phone,
                                code=self._code
                            )

                        # Store the session string after successful auth
                        self._session_string = await self._save_session()
                        if not self._session_string:
                            errors["base"] = "session_save_failed"
                        else:
                            await self._disconnect_client()
                            return await self.async_step_config()

                    except PhoneCodeInvalidError:
                        # При неверном коде завершаем диалог
                        await self._disconnect_client()
                        return self.async_abort(reason="invalid_code")
                    except PhoneCodeExpiredError:
                        errors["base"] = "expired_code"
                    except SessionPasswordNeededError:
                        return await self.async_step_password()
                    except Exception as ex:
                        errors["base"] = "sign_in_failed"
                        _LOGGER.error("Sign in error: %s", ex)
            except Exception as ex:
                errors["base"] = "unknown"
                _LOGGER.error("Unexpected error: %s", ex)
            finally:
                if errors:
                    await self._disconnect_client()

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({
                vol.Required(CONF_CODE): cv.string
            }),
            description_placeholders={
                "phone": self._phone if self._phone else "???????????"
            },
            errors=errors
        )


    async def async_step_password(self, user_input=None):
        """Step to enter 2FA password."""
        errors = {}
        
        if user_input is not None:
            try:
                if not await self._ensure_client():
                    errors["base"] = "connection_failed"
                else:
                    try:
                        async with timeout(AUTH_TIMEOUT):
                            await self._client.sign_in(password=user_input[CONF_PASSWORD])

                        # Store the session string after successful auth
                        # Changed from local variable to instance variable
                        self._session_string = await self._save_session()
                        if not self._session_string:
                            errors["base"] = "session_save_failed"
                        else:
                            await self._disconnect_client()
                            return await self.async_step_config()

                    except Exception as ex:
                        errors["base"] = "invalid_password"
                        _LOGGER.error("2FA error: %s", ex, exc_info=True)
            except Exception as ex:
                errors["base"] = "unknown"
                _LOGGER.error("Unexpected error: %s", ex, exc_info=True)
            finally:
                if errors:
                    await self._disconnect_client()

        return self.async_show_form(
            step_id="password",
            data_schema=vol.Schema({
                vol.Required(CONF_PASSWORD): cv.string
            }),
            errors=errors
        )


    async def async_step_config(self, user_input=None):
        """Step to configure auto-responder settings."""
        errors = {}

        hass = self.hass
        DEFAULT_TEXTS = {
            "en": "Thank you for your message! I will reply to you ASAP.",
            "ru": "Спасибо за ваше сообщение! Постараюсь Вам ответить в самое ближайшее время.",
            "es": "¡Gracias por tu mensaje! Te responderé lo antes posible.",
            "de": "Vielen Dank für Ihre Nachricht! Ich werde Ihnen so schnell wie möglich antworten.",
            "fr": "Merci pour votre message ! Je vous répondrai dès que possible."
        }

        language = hass.config.language.split('_')[0] if '_' in hass.config.language else hass.config.language
        default_response = DEFAULT_TEXTS.get(language, DEFAULT_TEXTS["en"])

        defaults = {
            CONF_IGNORED_USERS: "",
            CONF_RESPONSE_TEXT: default_response,
            CONF_COOLDOWN: 5,
            CONF_MAX_MSGS: 1,
            CONF_ALLOW_GROUP_CHATS: False,
            CONF_ALLOW_CHANNELS: False,
            CONF_ALLOW_BOTS: False
        }

        # If there is an existing configuration, use its values
        current_values = defaults.copy()
        if hasattr(self, '_config_data'):
            current_values.update(self._config_data)

        if user_input is not None:
            try:
                # Make sure all required fields are filled in
                if not hasattr(self, '_session_string') or not self._session_string:
                    errors["base"] = "session_missing"
                    _LOGGER.error("No session string available")
                else:
                    # Collect final data
                    config_data = {
                        CONF_API_ID: self._api_id,
                        CONF_API_HASH: self._api_hash,
                        CONF_SESSION: self._session_string,
                        CONF_PHONE: self._phone,
                        **{
                            k: user_input.get(k, defaults[k])
                            for k in [
                                CONF_IGNORED_USERS,
                                CONF_RESPONSE_TEXT,
                                CONF_COOLDOWN,
                                CONF_MAX_MSGS,
                                CONF_ALLOW_GROUP_CHATS,
                                CONF_ALLOW_CHANNELS,
                                CONF_ALLOW_BOTS
                            ]
                        }
                    }
                    return self.async_create_entry(
                        title=f"Telegram {self._phone}",
                        data=config_data
                    )
            except Exception as ex:
                await self._disconnect_client()
                _LOGGER.error("Error saving configuration: %s", ex, exc_info=True)
                errors["base"] = "unknown"

        schema = vol.Schema({
            vol.Optional(CONF_IGNORED_USERS, default=current_values[CONF_IGNORED_USERS]): cv.string,
            vol.Required(CONF_RESPONSE_TEXT, default=current_values[CONF_RESPONSE_TEXT]): cv.string,
            vol.Required(CONF_COOLDOWN, default=current_values[CONF_COOLDOWN]): cv.positive_int,
            vol.Required(CONF_MAX_MSGS, default=current_values[CONF_MAX_MSGS]): cv.positive_int,
            vol.Optional(CONF_ALLOW_GROUP_CHATS, default=current_values[CONF_ALLOW_GROUP_CHATS]): cv.boolean,
            vol.Optional(CONF_ALLOW_CHANNELS, default=current_values[CONF_ALLOW_CHANNELS]): cv.boolean,
            vol.Optional(CONF_ALLOW_BOTS, default=current_values[CONF_ALLOW_BOTS]): cv.boolean
        })

        return self.async_show_form(
            step_id="config",
            data_schema=schema,
            errors=errors
        )

    @staticmethod
    @callback

    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return TelegramOptionsFlowHandler(config_entry)

    async def async_step_abort(self, user_input=None):
        """Abort the configuration flow."""
        await self._disconnect_client()
        if hasattr(self, '_session_string'):
            del self._session_string
            
        return self.async_show_form(
            step_id="abort"
        )


class TelegramOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Telegram Auto Responder."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        # Getting the phone number from the configuration
        phone = self._config_entry.data.get(CONF_PHONE, "")

        if user_input is not None:
            try:

                if CONF_IGNORED_USERS in user_input:
                    # Get a list of selected values ​​and add them to the newly entered ones.
                    selected_users = user_input[CONF_IGNORED_USERS] or []
                    new_users = user_input.get(f"new_{CONF_IGNORED_USERS}", "").strip()
                    
                    # Merge and clear the list
                    all_users = list(set(selected_users))
                    if new_users:
                        # Add new users from the text field
                        new_users_list = [u.strip() for u in new_users.split(",") if u.strip()]
                        all_users.extend(new_users_list)
                    
                    ignored_users = ",".join(all_users) if all_users else None
                else:
                    ignored_users = ""

                # Other validations and value transformation
                cooldown = int(user_input.get(CONF_COOLDOWN, 5))
                max_msgs = int(user_input.get(CONF_MAX_MSGS, 1))
                response_text = user_input.get(CONF_RESPONSE_TEXT, "").strip()
                allow_group_chats = user_input.get(CONF_ALLOW_GROUP_CHATS, False)
                allow_channels = user_input.get(CONF_ALLOW_CHANNELS, False)
                allow_bots = user_input.get(CONF_ALLOW_BOTS, False)

                # Validity check
                if cooldown < 0:
                    errors[CONF_COOLDOWN] = "min_cooldown"
                if max_msgs < 1:
                    errors[CONF_MAX_MSGS] = "min_messages"
                if not response_text:
                    errors[CONF_RESPONSE_TEXT] = "empty_response"

                if not errors:
                    # Data for saving
                    updated_data = {
                        **self._config_entry.data,
                        CONF_IGNORED_USERS: ignored_users,
                        CONF_RESPONSE_TEXT: response_text,
                        CONF_COOLDOWN: cooldown,
                        CONF_MAX_MSGS: max_msgs,
                        CONF_ALLOW_GROUP_CHATS: allow_group_chats,
                        CONF_ALLOW_CHANNELS: allow_channels,
                        CONF_ALLOW_BOTS: allow_bots
                    }

                    # Updating the configuration
                    self.hass.config_entries.async_update_entry(
                        self._config_entry,
                        data=updated_data
                    )

                    # Reload integration
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(self._config_entry.entry_id)
                    )

                    return self.async_create_entry(title="", data=updated_data)

            except ValueError as ex:
                _LOGGER.error("Error updating configuration: %s", ex)
                errors["base"] = "invalid_input"


        # Get the current values
        current_config = self._config_entry.data
        current_options = self._config_entry.options or {}
        
        # Preparing Current Ignored Users
        current_ignored = current_options.get(CONF_IGNORED_USERS, current_config.get(CONF_IGNORED_USERS, ""))
        current_ignored_list = current_ignored.split(",") if current_ignored else []

        schema = {
            vol.Optional(
                CONF_IGNORED_USERS,
                default=current_ignored_list,
                description={
                    "suggested_value": current_ignored_list,
                    "description": "Select existing users to ignore"
                }
            ): SelectSelector(
                SelectSelectorConfig(
                    options=current_ignored_list,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=False
                )
            ),
            vol.Optional(f"new_{CONF_IGNORED_USERS}",description={
                    "description": "Add new users to ignore (comma-separated)"
                }
            ): str,
            vol.Required(
                CONF_RESPONSE_TEXT,
                default=current_options.get(CONF_RESPONSE_TEXT, 
                                        current_config.get(CONF_RESPONSE_TEXT, "")),
                description={"suggested_value": current_options.get(CONF_RESPONSE_TEXT, 
                                        current_config.get(CONF_RESPONSE_TEXT, "")), 
                            "description": "The automatic response message to send"}
            ): str,
            vol.Required(
                CONF_COOLDOWN,
                default=current_options.get(CONF_COOLDOWN, 
                                        current_config.get(CONF_COOLDOWN, 5)),
                description={"suggested_value": current_options.get(CONF_COOLDOWN, 
                                        current_config.get(CONF_COOLDOWN, 5)), 
                            "description": "Minimum minutes between responses to the same user"}
            ): cv.positive_int,
            vol.Required(
                CONF_MAX_MSGS,
                default=current_options.get(CONF_MAX_MSGS, 
                                        current_config.get(CONF_MAX_MSGS, 1)),
                description={"suggested_value": current_options.get(CONF_MAX_MSGS, 
                                        current_config.get(CONF_MAX_MSGS, 1)), 
                            "description": "Maximum number of automatic responses per user"}
            ): cv.positive_int,
            vol.Optional(
                CONF_ALLOW_GROUP_CHATS,
                default=current_options.get(CONF_ALLOW_GROUP_CHATS, 
                                         current_config.get(CONF_ALLOW_GROUP_CHATS, False)),
                description={"suggested_value": current_options.get(CONF_ALLOW_GROUP_CHATS, 
                                         current_config.get(CONF_ALLOW_GROUP_CHATS, False)), 
                            "description": "Allow responding in group chats"}
            ): cv.boolean,
            vol.Optional(
                CONF_ALLOW_CHANNELS,
                default=current_options.get(CONF_ALLOW_CHANNELS, 
                                         current_config.get(CONF_ALLOW_CHANNELS, False)),
                description={"suggested_value": current_options.get(CONF_ALLOW_CHANNELS, 
                                         current_config.get(CONF_ALLOW_CHANNELS, False)), 
                            "description": "Allow responding in channels"}
            ): cv.boolean,
            vol.Optional(
                CONF_ALLOW_BOTS,
                default=current_options.get(CONF_ALLOW_BOTS, 
                                         current_config.get(CONF_ALLOW_BOTS, False)),
                description={"suggested_value": current_options.get(CONF_ALLOW_BOTS, 
                                         current_config.get(CONF_ALLOW_BOTS, False)), 
                            "description": "Allow responding to bot messages"}
            ): cv.boolean
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"phone": phone}
        )

