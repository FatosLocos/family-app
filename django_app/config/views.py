from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Q
from django.utils import timezone

from family.models import Contact, WishItem
from finance.models import Transaction
from household.models import ShoppingItem, Task
from notifications.models import Notification
from planning.models import CalendarEvent


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "unavailable", "service": "family-app"}, status=503)
    return JsonResponse({"status": "ok", "service": "family-app"})


@login_required
def today(request):
    household = request.household
    now = timezone.now()
    tasks = Task.objects.for_household(household).filter(completed_at__isnull=True).order_by("due_at", "-priority")[:5]
    shopping = ShoppingItem.objects.for_household(household).filter(completed_at__isnull=True).select_related("list")[:5]
    events = CalendarEvent.objects.for_household(household).filter(ends_at__gte=now).order_by("starts_at")[:5]
    notifications = Notification.objects.for_household(household).filter(read_at__isnull=True).order_by("-created_at")[:4]
    return render(request, "today/index.html", {
        "tasks": tasks, "shopping_items": shopping, "events": events, "notifications": notifications,
        "today": timezone.localdate(),
    })


@login_required
def search(request):
    household = request.household
    query = request.GET.get("q", "").strip()
    results = {"tasks": [], "contacts": [], "events": [], "transactions": [], "wishes": []}
    if household and len(query) >= 2:
        results = {
            "tasks": Task.objects.for_household(household).filter(Q(title__icontains=query) | Q(notes__icontains=query)).order_by("completed_at", "due_at")[:6],
            "contacts": Contact.objects.for_household(household).filter(Q(name__icontains=query) | Q(people__name__icontains=query)).distinct()[:6],
            "events": CalendarEvent.objects.for_household(household).filter(Q(title__icontains=query) | Q(location__icontains=query)).order_by("starts_at")[:6],
            "transactions": Transaction.objects.for_household(household).filter(Q(description__icontains=query) | Q(counterparty__icontains=query)).order_by("-booked_at")[:6],
            "wishes": WishItem.objects.for_household(household).filter(title__icontains=query).select_related("wishlist")[:6],
        }
    context = {"query": query, **results}
    if request.headers.get("HX-Request"):
        return render(request, "search/partials/results.html", context)
    return render(request, "search/index.html", context)
