from django import forms

from travel.models import Trip, TripDocument, TripIdea, TripStop

DOCUMENT_MAX_BYTES = 10 * 1024 * 1024
DOCUMENT_SUFFIXES = {"pdf", "jpg", "jpeg", "png", "webp", "txt"}


class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = ("destination", "start_date", "end_date", "notes")
        labels = {"destination": "Bestemming", "start_date": "Vertrek", "end_date": "Terug", "notes": "Aantekeningen"}
        widgets = {
            "destination": forms.TextInput(attrs={"placeholder": "Bijv. Barcelona"}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Bijv. vlucht 's ochtends, huurauto geregeld"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("De terugreis mag niet vóór het vertrek liggen.")
        return cleaned_data


class TripStopForm(forms.ModelForm):
    class Meta:
        model = TripStop
        fields = ("name", "arrives_on", "departs_on")
        labels = {"name": "Tussenstop", "arrives_on": "Aankomst", "departs_on": "Vertrek"}
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Bijv. Girona"}),
            "arrives_on": forms.DateInput(attrs={"type": "date"}),
            "departs_on": forms.DateInput(attrs={"type": "date"}),
        }


class TripDocumentForm(forms.ModelForm):
    """One document, from exactly one source: an upload, a Dropbox path or a link."""

    class Meta:
        model = TripDocument
        fields = ("title", "file", "dropbox_path", "url")
        labels = {"title": "Titel", "file": "Bestand uploaden", "dropbox_path": "Bestand in Dropbox", "url": "Link"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Bijv. Vluchtbevestiging"}),
            "dropbox_path": forms.TextInput(attrs={"placeholder": "/Reizen/Barcelona/tickets.pdf"}),
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return uploaded
        if uploaded.size > DOCUMENT_MAX_BYTES:
            raise forms.ValidationError("Bestanden mogen maximaal 10 MB zijn.")
        suffix = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
        if suffix not in DOCUMENT_SUFFIXES:
            raise forms.ValidationError("Gebruik PDF, afbeelding of tekstbestand.")
        return uploaded


class TripIdeaForm(forms.ModelForm):
    class Meta:
        model = TripIdea
        fields = ("text",)
        labels = {"text": "Idee"}
        widgets = {"text": forms.Textarea(attrs={"rows": 2, "placeholder": "Bijv. dagtrip naar de kust"})}
