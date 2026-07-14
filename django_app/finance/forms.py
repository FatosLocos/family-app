from django import forms

from finance.models import Budget, RecurringRule


class StatementUploadForm(forms.Form):
    account_name = forms.CharField(label="Naam rekening", max_length=120, required=False)
    statement = forms.FileField(label="ABN AMRO export", help_text="CSV, XLS of XLSX")


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ("name", "monthly_limit", "category")


class RecurringRuleSettingsForm(forms.ModelForm):
    class Meta:
        model = RecurringRule
        fields = ("group", "is_excluded")
