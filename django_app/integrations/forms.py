from django import forms


class OutlookConfigForm(forms.Form):
    client_id = forms.CharField(label="Application (client) ID", max_length=240)
    client_secret = forms.CharField(label="Client secret", required=False, widget=forms.PasswordInput(render_value=False))
    tenant_id = forms.CharField(label="Tenant", max_length=80, initial="consumers")


class BunqConfigForm(forms.Form):
    client_id = forms.CharField(label="OAuth client ID", max_length=240)
    client_secret = forms.CharField(label="OAuth client secret", required=False, widget=forms.PasswordInput(render_value=False))
    environment = forms.ChoiceField(label="Omgeving", choices=(("production", "Productie"), ("sandbox", "Sandbox")), initial="production")


class HueConfigForm(forms.Form):
    client_id = forms.CharField(label="Hue OAuth client ID", max_length=240)
    client_secret = forms.CharField(label="Hue OAuth client secret", required=False, widget=forms.PasswordInput(render_value=False))
    app_id = forms.CharField(label="Hue application ID", max_length=120, required=False, help_text="Optioneel; neem dit over wanneer Hue een appid verstrekt.")
    device_name = forms.CharField(label="Apparaatnaam", max_length=120, required=False, initial="Family App", help_text="Zichtbaar in het Hue-overzicht Mijn apps.")


class SonosConfigForm(forms.Form):
    client_id = forms.CharField(label="Sonos integration key", max_length=240)
    client_secret = forms.CharField(label="Sonos integration secret", required=False, widget=forms.PasswordInput(render_value=False))
    events_enabled = forms.BooleanField(label="Sonos-events ontvangen", required=False, help_text="Schakel pas in nadat de event callback URL in het Sonos Developer Portal is geregistreerd.")


class GoogleHomeConfigForm(forms.Form):
    client_id = forms.CharField(label="Google OAuth client ID", max_length=240)
    client_secret = forms.CharField(label="Google OAuth client secret", required=False, widget=forms.PasswordInput(render_value=False))
    project_id = forms.CharField(label="Device Access project ID", max_length=240)


class LgThinQConfigForm(forms.Form):
    client_id = forms.CharField(label="LG Smart Solution client ID", max_length=240)
    client_secret = forms.CharField(label="LG Smart Solution client secret", required=False, widget=forms.PasswordInput(render_value=False))
    authorize_url = forms.URLField(label="OAuth authorization URL")
    token_url = forms.URLField(label="OAuth token URL")
    api_base_url = forms.URLField(label="ThinQ API base URL")
    devices_path = forms.CharField(label="Apparatenpad", max_length=240, initial="/devices", help_text="Pad uit de LG Smart Solution-documentatie, bijvoorbeeld /devices.")
