from django.http import HttpRequest

from common.db_scope import household_db_scope
from households.models import Household, Membership


class ActiveHouseholdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request.household = None
        request.membership = None
        if request.user.is_authenticated:
            memberships = Membership.objects.select_related("household").filter(user=request.user)
            selected_id = request.session.get("active_household_id")
            membership = memberships.filter(household_id=selected_id).first() if selected_id else None
            membership = membership or memberships.order_by("created_at").first()
            if membership:
                request.household = membership.household
                request.membership = membership
                request.session["active_household_id"] = membership.household_id
        if request.household:
            with household_db_scope(request.household.pk):
                return self.get_response(request)
        return self.get_response(request)
