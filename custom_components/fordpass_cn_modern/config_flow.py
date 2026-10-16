"""Owner-driven browser authorization for FordPass China."""

from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCEPT_TERMS, CONF_REDIRECT_URL, DOMAIN
from .private import load_private_settings
from .protocol.client import (
    FordApi,
    FordApiError,
    authorization_code_from_redirect,
    login_url_with_consents,
    policy_type_from_login_url,
)


_LOGGER = logging.getLogger(__name__)


class FordPassCnModernFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Exchange a Ford browser authorization code for rotating DLT tokens."""

    VERSION = 1

    def __init__(self) -> None:
        self._login_url: str | None = None
        self._policy_type: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_reauth(self, entry_data):
        entry_id = self.context.get("entry_id")
        self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        if self._reauth_entry is None:
            return self.async_abort(reason="reauth_entry_missing")
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        if self._reauth_entry is None and self._async_current_entries():
            return self.async_abort(reason="already_configured")
        if user_input is not None and user_input.get(CONF_ACCEPT_TERMS) is True:
            return await self.async_step_authorize()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ACCEPT_TERMS, default=False): bool}),
            errors={"base": "terms_required"} if user_input is not None else {},
        )

    async def async_step_authorize(self, user_input=None):
        errors = {}
        stage = "login_url"
        try:
            settings = await self.hass.async_add_executor_job(
                load_private_settings, self.hass.config.config_dir
            )
        except (FileNotFoundError, PermissionError, ValueError, TypeError):
            errors["base"] = "private_config_missing"
            return self.async_show_form(
                step_id="authorize",
                data_schema=vol.Schema({vol.Required(CONF_REDIRECT_URL): str}),
                errors=errors,
                description_placeholders={"login_url": ""},
            )
        try:
            api = FordApi(async_get_clientsession(self.hass), settings)
            if self._login_url is None:
                base_url = await api.bootstrap_login_url()
                self._policy_type = policy_type_from_login_url(base_url)
                self._login_url = login_url_with_consents(base_url)
            if user_input is not None:
                code = authorization_code_from_redirect(user_input[CONF_REDIRECT_URL])
                stage = "token_exchange"
                tokens = await api.exchange_b2c_code(code, self._policy_type)
                if not tokens.access_token or not tokens.refresh_token:
                    raise FordApiError("Ford returned incomplete DLT credentials")
                # Persist the one-time grant before querying vehicles. A
                # transient vehicle-list failure must not discard credentials
                # and force the owner through browser sign-in again.
                credentials = {
                    "access_token": tokens.access_token,
                    "refresh_token": tokens.refresh_token,
                    "access_expires_ms": tokens.access_expires_ms,
                    "refresh_expires_ms": tokens.refresh_expires_ms,
                }
                if self._reauth_entry is not None:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry, data_updates=credentials
                    )
                return self.async_create_entry(title="FordPass China", data=credentials)
        except (aiohttp.ClientError, TimeoutError):
            errors["base"] = "cannot_connect"
        except (FordApiError, ValueError, UnicodeError) as error:
            detail = str(error) if isinstance(error, FordApiError) else type(error).__name__
            reason = error.reason if isinstance(error, FordApiError) else None
            _LOGGER.warning("Ford setup failed at %s: %s reason=%s", stage, detail, reason)
            if stage == "token_exchange" and reason == "whitebox_decrypt_error":
                errors["base"] = "protocol_error"
            elif stage == "token_exchange":
                errors["base"] = "token_exchange_failed"
            else:
                errors["base"] = "cannot_connect"
        except (KeyError, TypeError):
            _LOGGER.warning("Ford setup returned unexpected fields at %s", stage)
            errors["base"] = "unexpected_response"
        return self.async_show_form(
            step_id="authorize",
            data_schema=vol.Schema({vol.Required(CONF_REDIRECT_URL): str}),
            errors=errors,
            description_placeholders={"login_url": self._login_url or ""},
        )
