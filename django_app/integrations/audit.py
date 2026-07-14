from integrations.models import IntegrationAudit


def log_integration_event(*, connection=None, household=None, user=None, action: str, detail: str = ""):
    """Persist a concise, non-sensitive integration event for household diagnostics."""
    household = household or connection.household
    return IntegrationAudit.objects.create(
        household=household,
        connection=connection,
        user=user or (connection.user if connection else None),
        provider=connection.provider if connection else "unknown",
        action=action,
        detail=detail[:500],
    )
