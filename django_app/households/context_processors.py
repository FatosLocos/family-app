def household_context(request):
    return {
        "active_household": getattr(request, "household", None),
        "active_membership": getattr(request, "membership", None),
    }
