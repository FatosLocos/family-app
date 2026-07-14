from django import forms


class HomeAssistantConfigForm(forms.Form):
    base_url = forms.URLField(label="Home Assistant-adres", max_length=500, widget=forms.URLInput(attrs={"placeholder": "http://homeassistant.local:8123"}))
    token = forms.CharField(label="Long-lived access token", required=False, widget=forms.PasswordInput(render_value=False))


class MaintenanceItemForm(forms.Form):
    title = forms.CharField(label="Onderhoudstaak", max_length=200)
    category = forms.CharField(label="Categorie", max_length=80, required=False)
    due_date = forms.DateField(label="Volgende datum", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    cadence_days = forms.IntegerField(label="Herhalen na dagen", min_value=1, initial=365)
    notes = forms.CharField(label="Notitie", required=False, widget=forms.Textarea(attrs={"rows": 2}))


class EmergencyContactForm(forms.Form):
    label = forms.CharField(label="Naam", max_length=120)
    value = forms.CharField(label="Telefoon, adres of instructie", max_length=300)
    kind = forms.ChoiceField(label="Type", choices=(("contact", "Contact"), ("nummer", "Noodnummer"), ("instructie", "Instructie")))
    notes = forms.CharField(label="Toelichting", max_length=300, required=False)


class RoomForm(forms.Form):
    name = forms.CharField(label="Ruimte", max_length=120)
    icon = forms.CharField(label="Icoon", max_length=40, initial="armchair")


class FurnishingItemForm(forms.Form):
    name = forms.CharField(label="Item", max_length=180)
    category = forms.CharField(label="Categorie", max_length=80, required=False)
    location_detail = forms.CharField(label="Plek", max_length=180, required=False)
    notes = forms.CharField(label="Notitie", required=False, widget=forms.Textarea(attrs={"rows": 2}))


class HouseholdDocumentForm(forms.Form):
    title = forms.CharField(label="Titel", max_length=180)
    category = forms.CharField(label="Categorie", max_length=80, required=False)
    file = forms.FileField(label="Bestand")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Bestanden mogen maximaal 10 MB zijn.")
        suffix = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
        if suffix not in {"pdf", "jpg", "jpeg", "png", "webp", "txt"}:
            raise forms.ValidationError("Gebruik PDF, afbeelding of tekstbestand.")
        return uploaded
