from django import forms

from family.models import BulletinPost, Contact, ContactPerson, WishItem


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ("name", "contact_type", "email", "phone", "address", "postal_code", "city", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class ContactPersonForm(forms.ModelForm):
    class Meta:
        model = ContactPerson
        fields = ("name", "birth_date", "email", "phone")
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}


class VCardImportForm(forms.Form):
    file = forms.FileField(label="vCard-bestand", help_text="Ondersteunt .vcf-bestanden uit Apple, Google en Outlook.")


class WishItemForm(forms.ModelForm):
    class Meta:
        model = WishItem
        fields = ("title", "url", "price", "category", "image_url", "repeatable")
        widgets = {
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
            "category": forms.TextInput(attrs={"placeholder": "Bijv. speelgoed"}),
            "image_url": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A URL-only wish is completed server-side when product metadata is available.
        self.fields["title"].required = False

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Vul een wens in of gebruik een productlink met herkenbare gegevens.")
        return title


class BulletinPostForm(forms.ModelForm):
    class Meta:
        model = BulletinPost
        fields = ("body",)
        widgets = {"body": forms.Textarea(attrs={"rows": 2, "placeholder": "Deel iets met het gezin"})}
