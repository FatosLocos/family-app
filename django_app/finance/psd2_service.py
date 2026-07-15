"""PSD2/Open Banking integration service."""
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from finance.models import BankConnection, BankAccount, Transaction
from integrations.crypto import encrypt, decrypt

logger = logging.getLogger(__name__)


class PlaidPSD2Client:
    """Plaid-based PSD2 integration for Open Banking access."""

    def __init__(self, client_id: str = None, secret: str = None):
        self.client_id = client_id or settings.PLAID_CLIENT_ID
        self.secret = secret or settings.PLAID_SECRET
        self.env = settings.PLAID_ENV  # 'sandbox', 'development', 'production'
        self.base_url = f"https://api.{self.env}.plaid.com" if self.env != "production" else "https://api.plaid.com"

    def create_link_token(self, user_id: str, country_codes: list[str] = None) -> dict | None:
        """Create a Plaid Link token for account connection."""
        try:
            response = requests.post(
                f"{self.base_url}/link/token/create",
                json={
                    "client_id": self.client_id,
                    "secret": self.secret,
                    "user": {"client_user_id": str(user_id)},
                    "client_name": "Family App",
                    "products": ["auth", "transactions"],
                    "country_codes": country_codes or ["NL", "DE", "BE", "FR"],
                    "language": "nl",
                },
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create Plaid link token: {e}")
            return None

    def exchange_public_token(self, public_token: str, metadata: dict) -> dict | None:
        """Exchange Plaid public token for access token."""
        try:
            response = requests.post(
                f"{self.base_url}/item/public_token/exchange",
                json={
                    "client_id": self.client_id,
                    "secret": self.secret,
                    "public_token": public_token,
                },
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to exchange public token: {e}")
            return None

    def get_accounts(self, access_token: str) -> list[dict] | None:
        """Fetch accounts for an access token."""
        try:
            response = requests.post(
                f"{self.base_url}/accounts/get",
                json={
                    "client_id": self.client_id,
                    "secret": self.secret,
                    "access_token": access_token,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("accounts", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get accounts: {e}")
            return None

    def get_transactions(self, access_token: str, start_date: str, end_date: str) -> list[dict] | None:
        """Fetch transactions for an access token."""
        try:
            response = requests.post(
                f"{self.base_url}/transactions/get",
                json={
                    "client_id": self.client_id,
                    "secret": self.secret,
                    "access_token": access_token,
                    "start_date": start_date,
                    "end_date": end_date,
                    "options": {"include_personal_finance_category": True},
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json().get("transactions", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get transactions: {e}")
            return None


def sync_psd2_accounts(connection_id: int, household_id: int) -> bool:
    """Sync accounts from PSD2 provider."""
    from common.db_scope import household_db_scope

    try:
        with household_db_scope(household_id):
            connection = BankConnection.objects.get(id=connection_id, household_id=household_id)

            if connection.provider != BankConnection.Provider.PLAID:
                return False

            access_token = decrypt(connection.oauth_access_token_encrypted)
            client = PlaidPSD2Client()
            accounts = client.get_accounts(access_token)

            if not accounts:
                return False

            for account_data in accounts:
                BankAccount.objects.update_or_create(
                    connection=connection,
                    provider_account_id=account_data.get("account_id"),
                    defaults={
                        "name": account_data.get("name", "Unknown"),
                        "iban": account_data.get("iban", ""),
                        "currency": account_data.get("balances", {}).get("iso_currency_code", "EUR"),
                        "balance": Decimal(str(account_data.get("balances", {}).get("current", 0))),
                    },
                )

            connection.last_sync_at = timezone.now()
            connection.save(update_fields=["last_sync_at"])

            return True
    except Exception as e:
        logger.error(f"Failed to sync PSD2 accounts: {e}")
        return False


def sync_psd2_transactions(connection_id: int, household_id: int, days: int = 90) -> int:
    """Sync transactions from PSD2 provider."""
    from common.db_scope import household_db_scope

    try:
        with household_db_scope(household_id):
            connection = BankConnection.objects.get(id=connection_id, household_id=household_id)

            if connection.provider != BankConnection.Provider.PLAID:
                return 0

            access_token = decrypt(connection.oauth_access_token_encrypted)
            client = PlaidPSD2Client()

            start_date = (timezone.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            end_date = timezone.now().strftime("%Y-%m-%d")

            transactions = client.get_transactions(access_token, start_date, end_date)
            if not transactions:
                return 0

            created_count = 0
            for txn_data in transactions:
                account = BankAccount.objects.filter(
                    connection=connection,
                    provider_account_id=txn_data.get("account_id"),
                ).first()

                if not account:
                    continue

                _, created = Transaction.objects.update_or_create(
                    account=account,
                    provider_transaction_id=txn_data.get("transaction_id"),
                    defaults={
                        "booked_at": datetime.fromisoformat(txn_data.get("date")).date(),
                        "description": txn_data.get("name", ""),
                        "counterparty": txn_data.get("merchant_name", txn_data.get("name", "")),
                        "amount": Decimal(str(txn_data.get("amount", 0))),
                        "currency": txn_data.get("iso_currency_code", "EUR"),
                        "category": txn_data.get("personal_finance_category", {}).get("primary", ""),
                        "metadata": {
                            "plaid_category": txn_data.get("personal_finance_category", {}),
                            "pending": txn_data.get("pending", False),
                        },
                    },
                )
                if created:
                    created_count += 1

            return created_count
    except Exception as e:
        logger.error(f"Failed to sync PSD2 transactions: {e}")
        return 0
