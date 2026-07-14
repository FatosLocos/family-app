from django import forms

from household.models import MealPlan, Receipt, Routine, ShoppingItem, ShoppingPrice, Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("title", "assigned_to", "due_at", "priority", "notes")
        widgets = {"due_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "notes": forms.Textarea(attrs={"rows": 2})}


class ShoppingItemForm(forms.ModelForm):
    class Meta:
        model = ShoppingItem
        fields = ("name", "quantity", "category", "recurring", "recurrence_days")
        widgets = {"recurrence_days": forms.NumberInput(attrs={"min": 1, "max": 365})}


class MealPlanForm(forms.ModelForm):
    class Meta:
        model = MealPlan
        fields = ("title", "planned_for", "notes")
        widgets = {"planned_for": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 2})}


class RoutineForm(forms.ModelForm):
    class Meta:
        model = Routine
        fields = ("title", "cadence", "interval_days", "next_due_on", "assigned_to")
        widgets = {
            "interval_days": forms.NumberInput(attrs={"min": 1, "max": 365}),
            "next_due_on": forms.DateInput(attrs={"type": "date"}),
        }


class ShoppingPriceForm(forms.ModelForm):
    class Meta:
        model = ShoppingPrice
        fields = ("retailer", "price", "unit_label", "is_offer", "offer_label", "product_url")
        widgets = {"price": forms.NumberInput(attrs={"step": "0.01", "min": "0"})}


class ReceiptForm(forms.ModelForm):
    class Meta:
        model = Receipt
        fields = ("retailer", "purchased_on", "total_amount", "image")
        widgets = {"purchased_on": forms.DateInput(attrs={"type": "date"}), "total_amount": forms.NumberInput(attrs={"step": "0.01"})}

    def clean_image(self):
        uploaded = self.cleaned_data["image"]
        if uploaded.size > 12 * 1024 * 1024:
            raise forms.ValidationError("Een bon mag maximaal 12 MB zijn.")
        if uploaded.content_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
            raise forms.ValidationError("Gebruik een foto, PNG, WEBP of PDF.")
        return uploaded
