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
