def household_context(request):
    household = getattr(request, "household", None)
    unread_notification_count = 0
    if household and getattr(request, "user", None) and request.user.is_authenticated:
        from notifications.models import Notification

        unread_notification_count = Notification.objects.for_household(household).filter(read_at__isnull=True).count()
    return {
        "active_household": household,
        "active_membership": getattr(request, "membership", None),
        "unread_notification_count": unread_notification_count,
    }
