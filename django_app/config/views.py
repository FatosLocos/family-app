from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.db.models import Q
from django.utils import timezone

from config.services import build_today_summary
from family.models import Contact, WishItem
from finance.models import Transaction
from home.models import HomeEntity
from household.models import Task
from notifications.models import Notification
from planning.models import CalendarEvent


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "unavailable", "service": "family-app"}, status=503)
    return JsonResponse({"status": "ok", "service": "family-app"})


def offline(request):
    return render(request, "offline.html")


def service_worker(request):
    content = (settings.BASE_DIR / "static" / "js" / "sw.js").read_text(encoding="utf-8")
    response = HttpResponse(content, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@login_required
def today(request):
    now = timezone.now()
    local_hour = timezone.localtime(now).hour
    if local_hour < 12:
        greeting = "Goedemorgen"
    elif local_hour < 18:
        greeting = "Goedemiddag"
    else:
        greeting = "Goedenavond"
    return render(request, "today/index.html", {**build_today_summary(request.household), "greeting": greeting})


@login_required
def search(request):
    household = request.household
    query = request.GET.get("q", "").strip()
    results = {"tasks": [], "contacts": [], "events": [], "transactions": [], "wishes": [], "devices": [], "notifications": []}
    if household and len(query) >= 2:
        results = {
            "tasks": Task.objects.for_household(household).filter(Q(title__icontains=query) | Q(notes__icontains=query)).order_by("completed_at", "due_at")[:6],
            "contacts": Contact.objects.for_household(household).filter(Q(name__icontains=query) | Q(people__name__icontains=query)).distinct()[:6],
            "events": CalendarEvent.objects.for_household(household).filter(Q(title__icontains=query) | Q(location__icontains=query)).order_by("starts_at")[:6],
            "transactions": Transaction.objects.for_household(household).filter(Q(description__icontains=query) | Q(counterparty__icontains=query)).order_by("-booked_at")[:6],
            "wishes": WishItem.objects.for_household(household).filter(title__icontains=query).select_related("wishlist")[:6],
            "devices": HomeEntity.objects.for_household(household).filter(Q(name__icontains=query) | Q(domain__icontains=query) | Q(state__icontains=query)).order_by("name")[:6],
            "notifications": Notification.objects.for_household(household).filter(Q(title__icontains=query) | Q(body__icontains=query)).order_by("-created_at")[:6],
        }
    context = {"query": query, **results}
    if request.headers.get("HX-Request"):
        return render(request, "search/partials/results.html", context)
    return render(request, "search/index.html", context)
