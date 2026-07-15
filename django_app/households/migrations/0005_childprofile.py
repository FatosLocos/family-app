# Generated migration for ChildProfile model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('households', '0004_household_invite_only'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChildProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='avatars/')),
                ('color', models.CharField(default='#3B82F6', max_length=7)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('household', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='child_profiles', to='households.household')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='child_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('household', 'user'), name='unique_child_in_household')],
            },
        ),
    ]
