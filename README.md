# Telegram Auto Responder Integration for Home Assistant 

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

[Telegram-Auto-Responder]: https://github.com/alexanderznamensky/Telegram-Auto-Responder

**This integration will set up switch for each your own Telegram account.**

## Installation

1. Add this repository URL as a custom repository in HACS
**Method 1.** [HACS](https://hacs.xyz/) custom repo:

> HACS > Integrations > 3 dots (upper top corner) > Custom repositories > URL: `alexanderznamensky/Telegram-Auto-Responder`, Category: Integration > Add > wait > Telegram-Auto-Responder > Install

**Method 2.** Manually copy `/Telegram-Auto-Responder` folder from [latest release](https://github.com/alexanderznamensky/Telegram-Auto-Responder) to `/config/custom_components` folder.

2. Restart Home Assistant
3. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Telegram auto responder"

## Configuration is done in the UI

You will need to register your existing account of Telegram at https://my.telegram.org/:

![image](https://github.com/user-attachments/assets/f227a556-5407-4dd7-b11b-3d2829be0cb1)

Then you input telephone number and receive auth code in yout Telegram App.
After entering the code and successful authorization, you just need to choose API development tools and copy api_id and api_hash.

Important

Integration is using telethone library. More details at https://docs.telethon.dev/en/stable/
Please read Compatibility and Convenience. As with any third-party library for Telegram, be careful not to break Telegram’s ToS or Telegram can ban the account.

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

***
