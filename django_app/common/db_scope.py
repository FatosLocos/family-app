from contextlib import contextmanager

from django.db import connection


@contextmanager
def household_db_scope(household_id):
    """Set the PostgreSQL RLS tenant variable for the current connection.

    Nestable: restores the previous value on exit instead of clearing it,
    so an inner scope (e.g. a helper called from within an already-scoped
    request) doesn't wipe out an outer scope that is still in use.
    """
    if connection.vendor != "postgresql":
        yield
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.household_id', true)")
        previous_value = cursor.fetchone()[0] or ""
        cursor.execute("SELECT set_config('app.household_id', %s, false)", [str(household_id)])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.household_id', %s, false)", [previous_value])
