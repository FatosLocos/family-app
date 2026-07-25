from django import forms

from family.models import WishList
from planning.models import CalendarEvent, EventInvite, EventProgramItem, EventQuestion, EventVenue, IcsSubscription


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


class EventVenueForm(forms.ModelForm):
    class Meta:
        model = EventVenue
        fields = ("name", "address", "postal_code", "city", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class EventInviteForm(forms.ModelForm):
    """Everything the organiser fills in on the invitation itself.

    is_shared and share_token are deliberately absent: turning the public link on is its own
    endpoint, so a stray field on this form can never publish an invitation by accident.
    """

    class Meta:
        model = EventInvite
        fields = ("intro", "venue", "wishlist", "rsvp_deadline")
        widgets = {
            "intro": forms.Textarea(attrs={"rows": 3}),
            "rsvp_deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household is not None:
            self.fields["venue"].queryset = EventVenue.objects.for_household(household)
            self.fields["wishlist"].queryset = WishList.objects.for_household(household)
        self.fields["venue"].empty_label = "Geen locatie"
        self.fields["wishlist"].empty_label = "Geen wenslijst"


class EventProgramItemForm(forms.ModelForm):
    class Meta:
        model = EventProgramItem
        fields = ("starts_at", "description", "sort_order")
        widgets = {"starts_at": forms.TextInput(attrs={"placeholder": "14:00"})}


class EventQuestionForm(forms.ModelForm):
    class Meta:
        model = EventQuestion
        fields = ("label", "kind", "is_required", "sort_order")
