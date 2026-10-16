"""Constants for the independent FordPass China integration."""

from homeassistant.const import Platform

DOMAIN = "fordpass_cn_modern"
CONF_REDIRECT_URL = "redirect_url"
CONF_ACCEPT_TERMS = "accept_terms"
PLATFORMS = [Platform.SENSOR, Platform.LOCK]
