from django import template


register = template.Library()


SOURCE_LABELS = {
    "google_cast": "Google Cast",
    "google_home": "Google Home",
    "home_assistant": "Home Assistant",
    "home_connect": "Home Connect",
    "hue": "Philips Hue",
    "lg_thinq": "LG ThinQ",
    "nest_protect": "Nest Protect",
    "philips_tv": "Philips TV",
    "smartcar": "Smartcar",
    "sonos": "Sonos",
    "spotify": "Spotify",
}


INTEGRATION_LABELS = {
    "bunq": "bunq",
    "google_home": "Google Home",
    "home_connect": "Home Connect",
    "hue": "Philips Hue",
    "lg_thinq": "LG ThinQ",
    "outlook": "Outlook",
    "smartcar": "Smartcar",
    "sonos": "Sonos",
    "spotify": "Spotify Connect",
}


@register.filter
def source_label(value):
    return SOURCE_LABELS.get(str(value or ""), "Home Assistant")


@register.filter
def integration_label(value):
    return INTEGRATION_LABELS.get(str(value or ""), "Koppeling")
