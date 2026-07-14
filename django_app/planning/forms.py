from django import forms

from planning.models import CalendarEvent, IcsSubscription


class CalendarEventForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = ("title", "starts_at", "ends_at", "is_all_day", "location", "notes", "participants")
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class IcsSubscriptionForm(forms.ModelForm):
    class Meta:
        model = IcsSubscription
        fields = ("name", "url")
        widgets = {"url": forms.URLInput(attrs={"placeholder": "https://…/agenda.ics"})}


class IcsFileForm(forms.Form):
    name = forms.CharField(label="Naam kalender", max_length=160)
    calendar_file = forms.FileField(label="ICS-bestand")
