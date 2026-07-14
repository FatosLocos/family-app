from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def household_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.household:
            raise PermissionDenied("Geen actief huishouden.")
        return view(request, *args, **kwargs)
    return wrapped


def parent_required(view):
    @household_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.membership.can_manage:
            raise PermissionDenied("Alleen ouders kunnen dit wijzigen.")
        return view(request, *args, **kwargs)
    return wrapped


def owner_required(view):
    @household_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.membership.role != "owner":
            raise PermissionDenied("Alleen de eigenaar kan dit beheren.")
        return view(request, *args, **kwargs)
    return wrapped
