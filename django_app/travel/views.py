from os.path import basename
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Max
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from households.decorators import household_required, parent_required
from travel.forms import TripDocumentForm, TripForm, TripIdeaForm, TripStopForm
from travel.models import Trip, TripDocument, TripIdea, TripStop
from travel.services import ensure_trip_task_list, trips_for_reading


def _travel_tab_redirect(tab: str):
    return redirect(f"{reverse('travel:index')}?{urlencode({'tab': tab})}")


@household_required
def index(request):
    tab = request.GET.get("tab", "reizen")
    trips = list(trips_for_reading(request.household))
    for trip in trips:
        trip.open_task_count = sum(1 for task in trip.task_list.tasks.all() if task.completed_at is None) if trip.task_list_id else 0
    return render(request, "travel/index.html", {
        "tab": tab,
        "trips": trips,
        "trip_form": TripForm(),
        "stop_form": TripStopForm(),
        "document_form": TripDocumentForm(),
        "idea_form": TripIdeaForm(),
        "metrics": [{"value": len(trips), "label": "reizen"}, {"value": sum(len(trip.ideas.all()) for trip in trips), "label": "ideeën"}],
    })


@parent_required
@require_POST
def add_trip(request):
    form = TripForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Controleer de reisgegevens.")
        return _travel_tab_redirect("reizen")
    trip = form.save(commit=False)
    trip.household = request.household
    trip.save()
    if ensure_trip_task_list(trip):
        messages.success(request, f"Reis toegevoegd, met takenlijst \"{trip.task_list.name}\" in de Taken-tab.")
    else:
        messages.success(request, "Reis toegevoegd. Er kon geen takenlijst worden gekoppeld omdat er al lijstjes met deze naam bestaan.")
    return _travel_tab_redirect("reizen")


@parent_required
@require_POST
def update_trip(request, trip_id):
    trip = get_object_or_404(Trip.objects.for_household(request.household), pk=trip_id)
    form = TripForm(request.POST, instance=trip)
    if form.is_valid():
        form.save()
        messages.success(request, "Reis aangepast.")
    else:
        messages.error(request, "Controleer de reisgegevens.")
    return _travel_tab_redirect("reizen")


@parent_required
@require_POST
def delete_trip(request, trip_id):
    trip = get_object_or_404(Trip.objects.for_household(request.household), pk=trip_id)
    for document in trip.documents.all():
        if document.file:
            document.file.delete(save=False)
    trip.delete()
    messages.success(request, "Reis verwijderd. De gekoppelde takenlijst blijft in de Taken-tab staan.")
    return _travel_tab_redirect("reizen")


@parent_required
@require_POST
def add_stop(request, trip_id):
    trip = get_object_or_404(Trip.objects.for_household(request.household), pk=trip_id)
    form = TripStopForm(request.POST)
    if form.is_valid():
        stop = form.save(commit=False)
        stop.household = request.household
        stop.trip = trip
        highest = trip.stops.aggregate(Max("sort_order"))["sort_order__max"]
        stop.sort_order = (highest + 1) if highest is not None else 0
        stop.save()
        messages.success(request, "Tussenstop toegevoegd.")
    else:
        messages.error(request, "Controleer de tussenstop.")
    return _travel_tab_redirect("reizen")


@parent_required
@require_POST
def delete_stop(request, stop_id):
    stop = get_object_or_404(TripStop.objects.for_household(request.household), pk=stop_id)
    stop.delete()
    messages.success(request, "Tussenstop verwijderd.")
    return _travel_tab_redirect("reizen")


@parent_required
@require_POST
def add_document(request, trip_id):
    trip = get_object_or_404(Trip.objects.for_household(request.household), pk=trip_id)
    form = TripDocumentForm(request.POST, request.FILES)
    if form.is_valid():
        document = form.save(commit=False)
        document.household = request.household
        document.trip = trip
        document.uploaded_by = request.user
        document.save()
        messages.success(request, "Document gekoppeld aan de reis.")
    else:
        messages.error(request, form.non_field_errors()[0] if form.non_field_errors() else "Controleer het document.")
    return _travel_tab_redirect("documenten")


@household_required
def download_document(request, document_id):
    document = get_object_or_404(TripDocument.objects.for_household(request.household), pk=document_id)
    if not document.file:
        messages.error(request, "Dit document staat niet in FamilyApp zelf, maar in Dropbox of achter een link.")
        return _travel_tab_redirect("documenten")
    return FileResponse(document.file.open("rb"), as_attachment=True, filename=basename(document.file.name))


@parent_required
@require_POST
def delete_document(request, document_id):
    document = get_object_or_404(TripDocument.objects.for_household(request.household), pk=document_id)
    if document.file:
        document.file.delete(save=False)
    document.delete()
    messages.success(request, "Document verwijderd.")
    return _travel_tab_redirect("documenten")


@household_required
@require_POST
def add_idea(request, trip_id):
    trip = get_object_or_404(Trip.objects.for_household(request.household), pk=trip_id)
    form = TripIdeaForm(request.POST)
    if form.is_valid():
        idea = form.save(commit=False)
        idea.household = request.household
        idea.trip = trip
        idea.author = request.user
        idea.save()
        messages.success(request, "Idee toegevoegd.")
    else:
        messages.error(request, "Schrijf eerst een idee op.")
    return _travel_tab_redirect("ideeen")


@household_required
@require_POST
def delete_idea(request, idea_id):
    idea = get_object_or_404(TripIdea.objects.for_household(request.household), pk=idea_id)
    idea.delete()
    messages.success(request, "Idee verwijderd.")
    return _travel_tab_redirect("ideeen")
