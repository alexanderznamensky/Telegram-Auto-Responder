from telethon import TelegramClient, events
from telethon.tl.types import User, Channel, Chat
from telethon.tl import types
from telethon.sessions import StringSession
import telethon.errors.rpcerrorlist
import logging
from datetime import datetime, timedelta
import pickle
import os
import aiofiles
from typing import Optional
import asyncio

from .config_flow import TelegramAuthFlowHandler
from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_entry_flow

_LOGGER = logging.getLogger(__name__)

from .const import (
    CONF_IGNORED_USERS,
    CONF_COOLDOWN,
    CONF_MAX_MSGS,
    CONF_ALLOW_GROUP_CHATS,
    CONF_ALLOW_CHANNELS,
    CONF_ALLOW_BOTS,
    DOMAIN,
)

class TelegramAutoResponder:
    def __init__(self, hass, entry_data, config_entry=None):
        self.hass = hass
        self.entry_data = entry_data
        self.config_entry = config_entry
        self._client: Optional[TelegramClient] = None
        self.last_message = {}
        self.storage_path = os.path.join(hass.config.config_dir, 'telegram_auto_responder.pkl')
        self.hass.async_add_executor_job(self._load_last_message)


    async def _load_last_message(self):
        """Asynchronous loading of last message timestamp."""
        try:
            async with aiofiles.open(self.storage_path, 'rb') as f:
                data = await f.read()
                self.last_message = pickle.loads(data)
        except (FileNotFoundError, EOFError, pickle.PickleError) as e:
            _LOGGER.error("Could not load last message timestamp: %s", e)
            self.last_message = {}


    async def _save_last_message(self):
        """Asynchronous saving of last message timestamp."""
        try:
            data = pickle.dumps(self.last_message)
            async with aiofiles.open(self.storage_path, 'wb') as f:
                await f.write(data)
        except (IOError, pickle.PickleError) as e:
            _LOGGER.error("Could not save last message timestamp: %s", e)


    async def _send_message_to_me(self, message: str):
        """Sending a message to yourself."""
        try:
            if not self._client:
                _LOGGER.error("Client is not available to send message")
                return False
                
            me = await self._client.get_me()
            if me:
                await self._client.send_message(me.id, message)
                return True
        except Exception as e:
            _LOGGER.error(f"Error sending message to me: {e}")
        return False


    async def start(self):
        """Starting the Auto Responder with proper ConfigEntry handling."""
        try:
            # Checking for the presence of config_entry
            if not hasattr(self, 'config_entry') or not self.config_entry:
                # _LOGGER.debug("Searching for matching ConfigEntry...")
                
                # Getting all records for our domain
                entries = self.hass.config_entries.async_entries(DOMAIN)
                
                # Search for a record by phone number
                for entry in entries:
                    if entry.data.get('phone') == self.entry_data.get('phone'):
                        self.config_entry = entry
                        # _LOGGER.debug(f"Found ConfigEntry: {entry.entry_id}")
                        break
                
                if not self.config_entry:
                    _LOGGER.error(f"No ConfigEntry found for phone: {self.entry_data.get('phone')}")
                    # _LOGGER.debug("Available entries: %s", [e.data.get('phone') for e in entries])
                    await self._turn_off_switch()
                    return False

            # Client initialization
            self._client = TelegramClient(
                StringSession(self.entry_data['session']),
                self.entry_data['api_id'],
                self.entry_data['api_hash']
            )
            await self._client.connect()

            # Checking authorization
            if not await self._client.is_user_authorized():
                _LOGGER.warning("Authorization required, initiating reauth...")

                # Starting the reauth process
                try:
                    result = await self.hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={
                            "source": "reauth",
                            "entry_id": self.config_entry.entry_id,
                            "title_placeholders": {
                                "name": f"Telegram {self.entry_data.get('phone', '')}"
                            }
                        },
                        data=self.config_entry.data
                    )
                    # _LOGGER.debug(f"Reauth flow started with result: {result}")
                    return False
                except Exception as e:
                    _LOGGER.error(f"Failed to start reauth flow: {e}")
                    return False

            # Successful authorization
            await self._send_message_to_me("Auto Responder is started!")

            @self._client.on(events.NewMessage())
            async def handler(event):

                try:
                    chat = await event.get_chat()
                    sender = await event.get_sender()

                    # Skip if it's our own message
                    if event.out:
                        # _LOGGER.debug(f"It's our own message chat_id: {getattr(chat, 'id', 'unknown')}, sender_id: {getattr(sender, 'id', 'unknown')}")
                        return                    

                    # Skip if we couldn't get sender info
                    if sender is None:
                        # _LOGGER.debug("🚫 Skipping message with no sender info")
                        return

                    # Get and properly format ignored_users
                    ignored_users = self.entry_data.get(CONF_IGNORED_USERS)
                    if ignored_users is None:
                        ignored_users = []
                    elif isinstance(ignored_users, str):
                        ignored_users = [u.strip() for u in ignored_users.split(',') if u.strip()]
                    elif not isinstance(ignored_users, (list, tuple, set)):
                        _LOGGER.warning(f"ignored_users should be a list, got {type(ignored_users)}. Converting to list.")
                        ignored_users = [str(ignored_users)]

                    # Determine message type (true/false)
                    is_private = isinstance(chat, types.User)
                    is_group = isinstance(chat, (types.Chat, types.ChatForbidden))
                    is_megagroup = isinstance(chat, types.Channel) and getattr(chat, 'megagroup', False)
                    is_channel = isinstance(chat, types.Channel) and not is_megagroup
                    is_bot = isinstance(sender, types.User) and getattr(sender, 'bot', False)

                    _LOGGER.debug(
                        f"📩 New message - Chat ID: {getattr(chat, 'id', '?')}, "
                        f"Type: {'private' if is_private else 'megagroup' if is_megagroup else 'group' if is_group else 'channel' if is_channel else 'unknown'}, "
                        f"Title: {getattr(chat, 'title', getattr(chat, 'first_name', '?'))}"
                    )

                    # Apply filters
                    if is_private:
                        if is_bot and not self.entry_data.get(CONF_ALLOW_BOTS, False):
                            _LOGGER.debug(f"🚫 Skipping bot message from {sender.id}")
                            return
                    elif is_megagroup or is_group:
                        if not self.entry_data.get(CONF_ALLOW_GROUP_CHATS, False):
                            _LOGGER.debug(f"🚫 Skipping group chat message from {chat.id}")
                            return
                    elif is_channel:
                        if not self.entry_data.get(CONF_ALLOW_CHANNELS, False):
                            _LOGGER.debug(f"🚫 Skipping channel message from {chat.id}")
                            return
                    else:
                        _LOGGER.debug(f"🚫 Skipping unknown chat type: {type(chat)}")
                        return

                    # Check ignored users
                    if ignored_users:
                        sender_id = str(getattr(sender, 'id', ''))
                        sender_username = str(getattr(sender, 'username', ''))
                        if sender_id in ignored_users or sender_username in ignored_users:
                            _LOGGER.debug(f"🚫 Skipping ignored user {sender.id}")
                            return

                    # Check cooldown and message rate limits
                    cooldown = self.entry_data.get(CONF_COOLDOWN, 0)
                    max_msgs = self.entry_data.get(CONF_MAX_MSGS, 0)

                    if cooldown > 0:
                        current_time = datetime.now()
                        chat_id = chat.id
                        
                        # Initialize tracking for new chats or convert old format
                        if chat_id not in self.last_message:
                            # New chat - initialize structure
                            self.last_message[chat_id] = {
                                'start_time': current_time,
                                'message_count': 1
                            }
                        else:
                            # Handle both old (datetime only) and new format
                            if isinstance(self.last_message[chat_id], datetime):
                                # Convert old format to new
                                self.last_message[chat_id] = {
                                    'start_time': self.last_message[chat_id],
                                    'message_count': 1
                                }
                            
                            last_data = self.last_message[chat_id]
                            time_diff = (current_time - last_data['start_time']).total_seconds()
                            
                            if time_diff < cooldown * 60:
                                # Within cooldown period
                                if max_msgs > 0 and last_data['message_count'] >= max_msgs:
                                    _LOGGER.debug(
                                        f"⏳ Skipping message - user {getattr(sender, 'id', '?')} "
                                        f"reached {last_data['message_count']}/{max_msgs} messages "
                                        f"in last {time_diff:.1f}/{cooldown*60} seconds"
                                    )
                                    return
                                
                                # Increment message count
                                last_data['message_count'] += 1
                            else:
                                # Cooldown period expired - reset counter
                                last_data['start_time'] = current_time
                                last_data['message_count'] = 1
                        
                        await self._save_last_message()

                    # All checks passed - send response
                    response_text = self.entry_data.get('response_text', '')
                    if response_text:
                        try:
                            _LOGGER.debug(f"✉️ Sending response to {chat.id}")
                            await event.respond(response_text)
                            
                            # Ensure we save in new format after response
                            if chat.id in self.last_message and isinstance(self.last_message[chat.id], datetime):
                                self.last_message[chat.id] = {
                                    'start_time': self.last_message[chat.id],
                                    'message_count': 1
                                }
                            elif chat.id not in self.last_message:
                                self.last_message[chat.id] = {
                                    'start_time': datetime.now(),
                                    'message_count': 1
                                }
                                
                            await self._save_last_message()
                        except telethon.errors.rpcerrorlist.ChatAdminRequiredError:
                            _LOGGER.debug(f"🚫 Skipping channel message - admin privileges required for {chat.id}")
                            return
                        except Exception as e:
                            _LOGGER.error(f"❌ Error sending response: {e}")
                            return

                    sender_info = f"{sender.id}"
                    if hasattr(sender, 'first_name'):
                        sender_info = f"{sender.id} ({sender.first_name})"
                    elif hasattr(sender, 'title'):  # Channels have 'title' instead of 'first_name'
                        sender_info = f"{sender.id} ({sender.title})"

                    _LOGGER.debug(f"✉️ Received message from {sender_info}: {event.text}")

                except Exception as e:
                    _LOGGER.error(f"❌ Error processing message: {e}", exc_info=True)

            # _LOGGER.debug("Telegram Auto Responder started")

        except Exception as e:
            _LOGGER.error("❌ Failed to start Telegram Auto Responder: %s", e)
            await self._turn_off_switch()
            return False        


    async def stop(self):
        """Stopping the Auto Responder."""
        try:
            # Only try to send message if client is still available
            if self._client and self._client.is_connected():
                await self._send_message_to_me("Auto Responder is stopped!")
                await self._save_last_message()
                await self._client.disconnect()
                
            self._client = None
            # _LOGGER.debug("Telegram Auto Responder is stopped")
        except Exception as e:
            _LOGGER.error("🔴 Failed to stop Telegram Auto Responder: %s", e)
            raise


    async def _turn_off_switch(self):
        """Switch off by phone number."""
        try:
            # Get a phone number without + and only the last 11 digits
            phone = self.entry_data.get('phone', '').lstrip('+')[-11:]
            if not phone.isdigit() or len(phone) != 11:
                _LOGGER.error(f"🔴 Invalid phone format: {self.entry_data.get('phone')}")
                return False

            entity_id = f"switch.telegram_{phone}_auto_responder"

            await self.hass.services.async_call(
                'switch',
                'turn_off',
                {'entity_id': entity_id},
                blocking=False
            )

            # Switch status check
            state = self.hass.states.get(entity_id)
            if state and state.state == 'off':
                # _LOGGER.debug(f"✉️ Successfully turned off {entity_id}")
                return True
            else:
                _LOGGER.warning(f"⚠️ Failed to turn off {entity_id}")
                return False

        except Exception as e:
            _LOGGER.error(f"🔴 Error turning off switch: {e}", exc_info=True)
            return False
