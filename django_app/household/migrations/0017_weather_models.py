# Generated migration for weather models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('households', '0005_childprofile'),
        ('household', '0016_receiptlineitem_shopping_item'),
    ]

    operations = [
        migrations.CreateModel(
            name='WeatherPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('location_name', models.CharField(blank=True, max_length=200)),
                ('temperature_unit', models.CharField(choices=[('C', 'Celsius'), ('F', 'Fahrenheit')], default='C', max_length=1)),
                ('wind_unit', models.CharField(choices=[('ms', 'm/s'), ('kmh', 'km/h'), ('mph', 'mph')], default='ms', max_length=3)),
                ('show_forecast', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('household', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='weather_preference', to='households.household')),
            ],
            options={
                'verbose_name_plural': 'Weather preferences',
            },
        ),
        migrations.CreateModel(
            name='WeatherData',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('temperature', models.DecimalField(decimal_places=1, max_digits=5)),
                ('feels_like', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('humidity', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('wind_speed', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ('description', models.CharField(blank=True, max_length=100)),
                ('icon', models.CharField(blank=True, max_length=20)),
                ('pressure', models.PositiveIntegerField(blank=True, null=True)),
                ('uvi', models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ('clouds', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('household', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='households.household')),
            ],
            options={
                'ordering': ('-created_at',),
                'abstract': False,
            },
        ),
    ]
