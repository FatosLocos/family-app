from django import forms

from households.models import Household, Membership


class InviteForm(forms.Form):
    role = forms.ChoiceField(label="Rol", choices=((Membership.Role.PARENT, "Ouder"), (Membership.Role.CHILD, "Kind")))
    label = forms.CharField(label="Voor wie?", max_length=120, required=False, help_text="Alleen zichtbaar binnen jullie huishouden.")


class HouseholdSettingsForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ("name",)
        labels = {"name": "Naam huishouden"}
