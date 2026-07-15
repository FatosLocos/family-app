# Generated migration for PSD2 OAuth support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0003_transaction_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bankconnection",
            name="provider",
            field=models.CharField(
                choices=[
                    ("bunq", "bunq"),
                    ("abn_amro_manual", "ABN AMRO import"),
                    ("plaid", "Plaid (PSD2)"),
                    ("open_banking", "Open Banking API"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="bankconnection",
            name="oauth_access_token_encrypted",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="bankconnection",
            name="oauth_refresh_token_encrypted",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="bankconnection",
            name="oauth_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bankconnection",
            name="oauth_link_token",
            field=models.CharField(blank=True, max_length=180),
        ),
    ]
