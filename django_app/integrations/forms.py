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


class SpotifyConfigForm(forms.Form):
    client_id = forms.CharField(label="Spotify client ID", max_length=240)
    client_secret = forms.CharField(label="Spotify client secret", required=False, widget=forms.PasswordInput(render_value=False))


class HomeConnectConfigForm(forms.Form):
    client_id = forms.CharField(label="Home Connect client ID", max_length=240)
    client_secret = forms.CharField(label="Home Connect client secret", required=False, widget=forms.PasswordInput(render_value=False))


class DropboxConfigForm(forms.Form):
    client_id = forms.CharField(label="Dropbox app key", max_length=240)
    client_secret = forms.CharField(label="Dropbox app secret", required=False, widget=forms.PasswordInput(render_value=False))


class SmartcarConfigForm(forms.Form):
    client_id = forms.CharField(label="API client ID", max_length=240, help_text="De API Credentials client ID voor server-side synchronisatie (meestal beginnend met client_).")
    client_secret = forms.CharField(label="API client secret", required=False, widget=forms.PasswordInput(render_value=False), help_text="De bijbehorende API secret. Deze wordt alleen server-side versleuteld opgeslagen.")
    connect_client_id = forms.CharField(label="Connect client ID", max_length=240, help_text="De client ID uit de Smartcar-appconfiguratie voor de browseraanmelding. Dit is niet de API Credentials client ID.")
    country = forms.CharField(label="Standaardland", max_length=2, initial="NL", required=False, help_text="Tweeletterige landcode voor de voertuigkiezer, bijvoorbeeld NL.")
    allow_remote_controls = forms.BooleanField(label="Vergrendelen en ontgrendelen toestaan", required=False, help_text="Vraag alleen aan als je deze externe voertuigbediening bewust wilt gebruiken.")


class GoogleHomeConfigForm(forms.Form):
    client_id = forms.CharField(label="Google OAuth client ID", max_length=240)
    client_secret = forms.CharField(label="Google OAuth client secret", required=False, widget=forms.PasswordInput(render_value=False))
    project_id = forms.CharField(label="Device Access project ID", max_length=240)
    events_enabled = forms.BooleanField(label="Live Nest-events ontvangen", required=False)
    pubsub_subscription = forms.CharField(label="Pub/Sub subscription", max_length=300, required=False, help_text="Volledige naam: projects/PROJECT/subscriptions/NAAM.")
    pubsub_service_account_json = forms.CharField(label="Serviceaccount JSON", required=False, widget=forms.Textarea(attrs={"rows": 4}), help_text="Alleen nodig voor live events. Wordt versleuteld opgeslagen en daarna niet opnieuw getoond.")


class ImapConfigForm(forms.Form):
    label = forms.CharField(label="Naam voor deze koppeling", max_length=160, required=False, help_text="Optioneel, handig als je meerdere IMAP-accounts koppelt (bijv. 'Werk' of 'Privé'). Standaard je gebruikersnaam.")
    host = forms.CharField(label="IMAP-server", max_length=240, help_text="Bijvoorbeeld imap.gmail.com.")
    port = forms.IntegerField(label="IMAP-poort", initial=993)
    use_ssl = forms.BooleanField(label="SSL gebruiken (aanbevolen)", required=False, initial=True)
    username = forms.CharField(label="Gebruikersnaam", max_length=240, help_text="Meestal je e-mailadres.")
    password = forms.CharField(label="Wachtwoord", widget=forms.PasswordInput(render_value=False), help_text="Bij Gmail en veel andere providers is dit een app-wachtwoord, niet je gewone wachtwoord.")
    smtp_host = forms.CharField(label="SMTP-server (versturen)", max_length=240, required=False, help_text="Leeg laten om dezelfde server als hierboven te gebruiken.")
    smtp_port = forms.IntegerField(label="SMTP-poort", initial=587)
    smtp_use_tls = forms.BooleanField(label="STARTTLS gebruiken (aanbevolen)", required=False, initial=True)


class LgThinQConfigForm(forms.Form):
    client_id = forms.CharField(label="LG Smart Solution client ID", max_length=240)
    client_secret = forms.CharField(label="LG Smart Solution client secret", required=False, widget=forms.PasswordInput(render_value=False))
    authorize_url = forms.URLField(label="OAuth authorization URL")
    token_url = forms.URLField(label="OAuth token URL")
    api_base_url = forms.URLField(label="ThinQ API base URL")
    devices_path = forms.CharField(label="Apparatenpad", max_length=240, initial="/devices", help_text="Pad uit de LG Smart Solution-documentatie, bijvoorbeeld /devices.")
