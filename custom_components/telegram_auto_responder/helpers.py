"""Helper functions for Telegram Auto Responder."""

import logging
from typing import Any

from python_socks import ProxyType

from .const import (
    CONF_PROXY_ENABLED,
    CONF_PROXY_TYPE,
    CONF_PROXY_HOST,
    CONF_PROXY_PORT,
    CONF_PROXY_USERNAME,
    CONF_PROXY_PASSWORD,
    PROXY_TYPE_SOCKS5,
    PROXY_TYPES,
)

_LOGGER = logging.getLogger(__name__)


def build_telethon_proxy(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build a Telethon proxy dict from config entry data.

    Telethon 1.x accepts a dict with proxy_type, addr, port, username,
    password and rdns. For SOCKS5 we keep rdns=True so DNS resolution is
    performed by the proxy, not by the local blocked network.
    """
    data = data or {}

    if not data.get(CONF_PROXY_ENABLED, False):
        return None

    proxy_type_name = str(data.get(CONF_PROXY_TYPE) or PROXY_TYPE_SOCKS5).lower()
    if proxy_type_name not in PROXY_TYPES:
        _LOGGER.warning("Unsupported proxy type %s, falling back to socks5", proxy_type_name)
        proxy_type_name = PROXY_TYPE_SOCKS5

    if proxy_type_name == "http":
        proxy_type = ProxyType.HTTP
    else:
        proxy_type = ProxyType.SOCKS5

    host = str(data.get(CONF_PROXY_HOST) or "").strip()
    raw_port = data.get(CONF_PROXY_PORT)

    if not host or raw_port in (None, ""):
        _LOGGER.warning("Proxy is enabled, but host or port is empty; connecting without proxy")
        return None

    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        _LOGGER.warning("Invalid proxy port %r; connecting without proxy", raw_port)
        return None

    if not 1 <= port <= 65535:
        _LOGGER.warning("Proxy port %s is outside valid range; connecting without proxy", port)
        return None

    proxy: dict[str, Any] = {
        "proxy_type": proxy_type,
        "addr": host,
        "port": port,
        "rdns": True,
    }

    username = str(data.get(CONF_PROXY_USERNAME) or "").strip()
    password = str(data.get(CONF_PROXY_PASSWORD) or "").strip()

    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password

    _LOGGER.info(
        "Telegram Auto Responder proxy configured: type=%s host=%s port=%s username=%s password=%s",
        proxy_type_name,
        host,
        port,
        "yes" if username else "no",
        "yes" if password else "no",
    )

    return proxy
