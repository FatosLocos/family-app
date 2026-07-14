from django.contrib import admin

from finance.models import BankAccount, BankConnection, Budget, RecurringRule, Transaction

admin.site.register((BankConnection, BankAccount, Transaction, RecurringRule, Budget))
