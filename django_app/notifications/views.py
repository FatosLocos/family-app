import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from households.decorators import household_required
from notifications.models import Notification, PushSubscription


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


@login_required
@require_http_methods(["POST"])
def subscribe_push(request):
    try:
        data = json.loads(request.body)
        subscription = data.get("subscription")
        if not subscription or not subscription.get("endpoint"):
            return JsonResponse({"error": "Invalid subscription data"}, status=400)

        PushSubscription.objects.update_or_create(
            user=request.user,
            defaults={
                "endpoint": subscription["endpoint"],
                "p256dh": subscription["keys"]["p256dh"],
                "auth": subscription["keys"]["auth"],
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            }
        )
        return JsonResponse({"success": True})
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({"error": "Invalid request"}, status=400)


@login_required
@require_http_methods(["POST"])
def unsubscribe_push(request):
    PushSubscription.objects.filter(user=request.user).delete()
    return JsonResponse({"success": True})
