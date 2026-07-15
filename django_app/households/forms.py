from django import forms

from households.models import Household, Membership, ChildProfile


class InviteForm(forms.Form):
    role = forms.ChoiceField(label="Rol", choices=((Membership.Role.PARENT, "Ouder"), (Membership.Role.CHILD, "Kind")))
    label = forms.CharField(label="Voor wie?", max_length=120, required=False, help_text="Alleen zichtbaar binnen jullie huishouden.")


class HouseholdSettingsForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ("name",)
        labels = {"name": "Naam huishouden"}


class ChildProfileForm(forms.ModelForm):
    COLOR_CHOICES = [
        ("#3B82F6", "Blauw"),
        ("#EF4444", "Rood"),
        ("#10B981", "Groen"),
        ("#F59E0B", "Oranje"),
        ("#8B5CF6", "Paars"),
        ("#EC4899", "Roze"),
        ("#14B8A6", "Teal"),
        ("#F97316", "Oranje-rood"),
    ]

    color = forms.ChoiceField(
        label="Kleur",
        choices=COLOR_CHOICES,
        widget=forms.RadioSelect,
        required=True
    )

    class Meta:
        model = ChildProfile
        fields = ("date_of_birth", "avatar", "color")
        labels = {
            "date_of_birth": "Geboortedatum",
            "avatar": "Profielfoto",
            "color": "Kleur",
        }
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }
