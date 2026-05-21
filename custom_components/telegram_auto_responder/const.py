"""Constants for Telegram Auto Responder."""
DOMAIN = "telegram_auto_responder"
DEFAULT_NAME = "Telegram Auto Responder"

# Configuration keys
CONF_API_ID = "api_id"
CONF_API_HASH = "api_hash"
CONF_IGNORED_USERS = "ignored_users"
CONF_RESPONSE_TEXT = "response_text"
CONF_COOLDOWN = "cooldown"
CONF_MAX_MSGS = "max_msgs"
DEFAULT_COOLDOWN = 5
DEFAULT_MAX_MSGS = 1
CONF_SESSION = "session"
CONF_PHONE = "phone"
CONF_CODE = "code"
CONF_PASSWORD = "password"
CONF_AUTO_RESPONDER_ENABLED = "auto_responder_enabled"
CONF_ALLOW_GROUP_CHATS = "allow_group_chats"
CONF_ALLOW_CHANNELS = "allow_channels"
CONF_ALLOW_BOTS = "allow_bots"
CONF_TEST_MESSAGE = "test_message"

MAX_COOLDOWN = 1440
MAX_MESSAGES = 1000
# Proxy configuration keys
CONF_PROXY_ENABLED = "proxy_enabled"
CONF_PROXY_TYPE = "proxy_type"
CONF_PROXY_HOST = "proxy_host"
CONF_PROXY_PORT = "proxy_port"
CONF_PROXY_USERNAME = "proxy_username"
CONF_PROXY_PASSWORD = "proxy_password"

PROXY_TYPE_SOCKS5 = "socks5"
PROXY_TYPE_HTTP = "http"
PROXY_TYPES = [PROXY_TYPE_SOCKS5, PROXY_TYPE_HTTP]
