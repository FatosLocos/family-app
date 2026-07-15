from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from households.decorators import household_required
from notifications.models import Notification


@household_required
def index(request):
    selected_filter = request.GET.get("filter", "ongelezen")
    notifications = Notification.objects.for_household(request.household).select_related("user")
    if selected_filter == "ongelezen":
        notifications = notifications.filter(read_at__isnull=True)
    elif selected_filter != "alles":
        selected_filter = "ongelezen"
        notifications = notifications.filter(read_at__isnull=True)
    unread_count = Notification.objects.for_household(request.household).filter(read_at__isnull=True).count()
    return render(
        request,
        "notifications/index.html",
        {
            "notifications": notifications[:100],
            "selected_filter": selected_filter,
            "unread_count": unread_count,
            "notification_metrics": [{"value": unread_count, "label": "ongelezen"}],
        },
    )


@household_required
@require_POST
def mark_read(request, notification_id):
    notification = get_object_or_404(Notification.objects.for_household(request.household), pk=notification_id)
    notification.read_at = timezone.now()
    notification.save(update_fields=["read_at"])
    return redirect(request.POST.get("next") or "today")


@household_required
@require_POST
def mark_all_read(request):
    Notification.objects.for_household(request.household).filter(read_at__isnull=True).update(read_at=timezone.now())
    return redirect(request.POST.get("next") or "notifications:index")
