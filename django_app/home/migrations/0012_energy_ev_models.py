# Generated migration for energy and EV models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("households", "0005_childprofile"),
        ("home", "0011_alter_homeentity_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="EnergyReading",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(default="grid", max_length=80)),
                ("consumption_kwh", models.DecimalField(decimal_places=2, max_digits=10)),
                ("production_kwh", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("timestamp", models.DateTimeField(db_index=True)),
                ("cost_eur", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_readings", to="households.household")),
            ],
            options={
                "ordering": ("-timestamp",),
            },
        ),
        migrations.CreateModel(
            name="EVVehicle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("make", models.CharField(blank=True, max_length=80)),
                ("model", models.CharField(blank=True, max_length=80)),
                ("battery_capacity_kwh", models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True)),
                ("current_soc_percent", models.PositiveSmallIntegerField(default=0)),
                ("current_range_km", models.PositiveIntegerField(default=0)),
                ("integration_provider", models.CharField(blank=True, max_length=32)),
                ("external_id", models.CharField(blank=True, max_length=300)),
                ("is_charging", models.BooleanField(default=False)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("household", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ev_vehicles", to="households.household")),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="EVChargingSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_time", models.DateTimeField()),
                ("end_time", models.DateTimeField(blank=True, null=True)),
                ("start_soc_percent", models.PositiveSmallIntegerField()),
                ("end_soc_percent", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("energy_added_kwh", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("location", models.CharField(blank=True, max_length=200)),
                ("cost_eur", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("vehicle", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="charging_sessions", to="home.evvehicle")),
            ],
            options={
                "ordering": ("-start_time",),
            },
        ),
        migrations.AddIndex(
            model_name="evchargingsession",
            index=models.Index(fields=["vehicle", "-start_time"], name="home_evchar_vehicle_start_time_idx"),
        ),
        migrations.AddIndex(
            model_name="energyreading",
            index=models.Index(fields=["household", "-timestamp"], name="home_energy_household_timestamp_idx"),
        ),
        migrations.AddIndex(
            model_name="energyreading",
            index=models.Index(fields=["source", "-timestamp"], name="home_energy_source_timestamp_idx"),
        ),
    ]
