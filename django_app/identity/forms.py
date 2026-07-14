from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from identity.models import User


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="E-mailadres", widget=forms.EmailInput(attrs={"autocomplete": "email"}))


class SignUpForm(UserCreationForm):
    display_name = forms.CharField(label="Naam", max_length=120)

    class Meta:
        model = User
        fields = ("display_name", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"].lower()
        user.email = self.cleaned_data["email"].lower()
        user.display_name = self.cleaned_data["display_name"]
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("display_name",)
        labels = {"display_name": "Naam"}
