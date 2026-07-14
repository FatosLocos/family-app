from django.contrib import admin

from home.models import HomeActionAudit, HomeAssistantConfig, HomeEntity

admin.site.register((HomeAssistantConfig, HomeEntity, HomeActionAudit))
