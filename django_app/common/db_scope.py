from contextlib import contextmanager

from django.db import connection


@contextmanager
def household_db_scope(household_id):
    """Set the PostgreSQL RLS tenant variable for the current connection."""
    if connection.vendor != "postgresql":
        yield
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.household_id', %s, false)", [str(household_id)])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.household_id', '', false)")
