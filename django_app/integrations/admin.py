from django.contrib import admin

from integrations.models import IntegrationAppConfig, IntegrationAudit, IntegrationConnection, SyncRun

admin.site.register((IntegrationAppConfig, IntegrationConnection, SyncRun, IntegrationAudit))
