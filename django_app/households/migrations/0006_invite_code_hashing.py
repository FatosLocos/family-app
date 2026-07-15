# Generated migration for invite code hashing

from django.db import migrations, models
import hashlib


def hash_existing_codes(apps, schema_editor):
    """Hash existing plain-text invite codes."""
    HouseholdInvite = apps.get_model("households", "HouseholdInvite")

    for invite in HouseholdInvite.objects.all():
        if hasattr(invite, "code") and invite.code:
            invite.code_hash = hashlib.pbkdf2_hmac(
                "sha256",
                invite.code.encode("utf-8"),
                b"family-app-invite",
                100000,
            ).hex()
            invite.save(update_fields=["code_hash"])


def reverse_hash(apps, schema_editor):
    """Reverse migration - clear hashes (codes are lost)."""
    HouseholdInvite = apps.get_model("households", "HouseholdInvite")
    HouseholdInvite.objects.all().update(code_hash="")


class Migration(migrations.Migration):

    dependencies = [
        ("households", "0005_childprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="householdinvite",
            name="code_hash",
            field=models.CharField(default="", db_index=True, max_length=64, unique=True),
            preserve_default=False,
        ),
        migrations.RunPython(hash_existing_codes, reverse_hash),
        migrations.RemoveField(
            model_name="householdinvite",
            name="code",
        ),
    ]
