from django import forms

from finance.models import Budget, RecurringRule, Transaction


class StatementUploadForm(forms.Form):
    account_name = forms.CharField(label="Naam rekening", max_length=120, required=False)
    statement = forms.FileField(label="ABN AMRO export", help_text="CSV, XLS of XLSX")


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ("name", "monthly_limit", "category")


class TransactionCategoryForm(forms.ModelForm):
    apply_to_history = forms.BooleanField(
        required=False,
        initial=True,
        label="Ook toepassen op dezelfde tegenpartij in de historie",
    )

    class Meta:
        model = Transaction
        fields = ("category",)
        widgets = {"category": forms.TextInput(attrs={"maxlength": 100, "placeholder": "Bijv. boodschappen"})}


class RecurringRuleSettingsForm(forms.ModelForm):
    class Meta:
        model = RecurringRule
        fields = ("group", "is_excluded")
