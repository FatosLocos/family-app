from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from households.decorators import household_required
from notifications.models import Notification


@household_required
@require_POST
def mark_read(request, notification_id):
    notification = get_object_or_404(Notification.objects.for_household(request.household), pk=notification_id)
    notification.read_at = timezone.now()
    notification.save(update_fields=["read_at"])
    return redirect(request.POST.get("next") or "today")
