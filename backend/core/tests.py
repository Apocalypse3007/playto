import threading
from unittest.mock import patch
from django.test import TransactionTestCase
from django.db import connection
from rest_framework.test import APIClient
from django.urls import reverse
from uuid import uuid4

from core.models import Merchant, Transaction as LedgerTransaction, Payout, IdempotencyKey
from core.services import request_payout, InsufficientFundsError, transition_payout_state


class ConcurrencyAndIdempotencyTests(TransactionTestCase):
    """
    Uses TransactionTestCase (not TestCase) because select_for_update requires
    real database transaction boundaries, not the single wrapped transaction
    that TestCase uses.
    """

    def setUp(self):
        self.merchant = Merchant.objects.create(name="Test Merchant")
        # Give merchant 100 rupees (10,000 paise)
        LedgerTransaction.objects.create(
            merchant=self.merchant,
            amount_paise=10000,
            txn_type=LedgerTransaction.Type.CREDIT
        )
        self.client = APIClient()

    def test_concurrency_double_spend(self):
        """
        A merchant with 100 rupees submits two simultaneous 60 rupee payout
        requests. Exactly one must succeed and the other must be rejected cleanly
        with InsufficientFundsError. The final balance must be 40 rupees.
        """
        errors = []
        payouts = []

        def attempt_payout():
            try:
                payout = request_payout(
                    merchant_id=self.merchant.id,
                    amount_paise=6000,          # 60 rupees
                    bank_account_id="BANK_123",
                    idempotency_key=str(uuid4()) # unique key per thread
                )
                payouts.append(payout)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_payout)
        t2 = threading.Thread(target=attempt_payout)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one succeeds, exactly one fails
        self.assertEqual(len(payouts), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], InsufficientFundsError)

        # Balance must be exactly 40 rupees (4,000 paise)
        self.assertEqual(self.merchant.balance_paise, 4000)

    def test_idempotency_exact_same_response(self):
        """
        A second request with the same Idempotency-Key must return the exact
        same HTTP status and body as the first. Only one payout and one
        PAYOUT_HOLD transaction must exist in the database.
        """
        import time
        url = reverse('payout_request', kwargs={'merchant_id': self.merchant.id})
        idempotency_key = str(uuid4())
        payload = {"amount_paise": 1000, "bank_account_id": "TEST_ACCT"}

        response1 = self.client.post(url, payload, format='json',
                                     headers={'Idempotency-Key': idempotency_key})
        self.assertEqual(response1.status_code, 201)

        time.sleep(0.1)

        response2 = self.client.post(url, payload, format='json',
                                     headers={'Idempotency-Key': idempotency_key})
        self.assertEqual(response2.status_code, 201)
        # Compare the key financial fields — JSON round-trip can change dict ordering
        for field in ('id', 'amount_paise', 'bank_account_id', 'state'):
            self.assertEqual(response1.data[field], response2.data[field])

        # Only one payout and one hold must exist
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(
            LedgerTransaction.objects.filter(txn_type=LedgerTransaction.Type.PAYOUT_HOLD).count(),
            1
        )


class PayoutProcessorTests(TransactionTestCase):
    """
    Tests for the background Celery payout processor (_simulate_settlement).
    random.choices is mocked to produce deterministic success/fail outcomes
    so the tests are not flaky.
    """

    def setUp(self):
        self.merchant = Merchant.objects.create(name="Processor Test Merchant")
        # Give merchant 500 rupees (50,000 paise)
        LedgerTransaction.objects.create(
            merchant=self.merchant,
            amount_paise=50000,
            txn_type=LedgerTransaction.Type.CREDIT
        )

    def _create_processing_payout(self, amount_paise=10000):
        """
        Helper: creates a payout, holds funds (PENDING), then moves it to
        PROCESSING — the state the background worker expects to find.
        """
        payout = request_payout(
            merchant_id=self.merchant.id,
            amount_paise=amount_paise,
            bank_account_id="BANK_EXT_001",
            idempotency_key=str(uuid4())
        )
        transition_payout_state(payout.id, Payout.State.PROCESSING)
        return payout

    def test_processor_success_completes_payout(self):
        """
        On a 'success' outcome:
        - Payout must reach COMPLETED state.
        - No PAYOUT_REFUND transaction must exist (funds are not returned).
        - Balance must stay at the post-hold level (deduction is permanent).
        """
        from core.tasks import _simulate_settlement

        payout = self._create_processing_payout(amount_paise=10000)  # hold 100 rupees
        balance_after_hold = self.merchant.balance_paise              # 400 rupees

        with patch('core.tasks.random.choices', return_value=['success']), \
             patch('core.tasks.time.sleep'):   # skip simulated network delay
            _simulate_settlement(str(payout.id))

        payout.refresh_from_db()
        self.assertEqual(payout.state, Payout.State.COMPLETED)
        self.assertEqual(self.merchant.balance_paise, balance_after_hold)

        refunds = LedgerTransaction.objects.filter(
            merchant=self.merchant,
            txn_type=LedgerTransaction.Type.PAYOUT_REFUND
        )
        self.assertEqual(refunds.count(), 0, "No refund should exist on success")

    def test_processor_failure_atomically_returns_funds(self):
        """
        On a 'fail' outcome:
        - Payout must reach FAILED state.
        - Exactly one PAYOUT_REFUND transaction must be created atomically
          with the state transition (same @transaction.atomic block).
        - Merchant balance must be fully restored to pre-payout level.
        """
        from core.tasks import _simulate_settlement

        balance_before = self.merchant.balance_paise      # 500 rupees
        payout = self._create_processing_payout(amount_paise=10000)   # hold 100 rupees

        # Hold must have reduced the balance
        self.assertEqual(self.merchant.balance_paise, balance_before - 10000)

        with patch('core.tasks.random.choices', return_value=['fail']), \
             patch('core.tasks.time.sleep'):
            _simulate_settlement(str(payout.id))

        payout.refresh_from_db()
        self.assertEqual(payout.state, Payout.State.FAILED)

        # Balance must be fully restored
        self.assertEqual(self.merchant.balance_paise, balance_before)

        # Exactly one refund for the exact amount
        refunds = LedgerTransaction.objects.filter(
            merchant=self.merchant,
            txn_type=LedgerTransaction.Type.PAYOUT_REFUND,
            payout=payout
        )
        self.assertEqual(refunds.count(), 1)
        self.assertEqual(refunds.first().amount_paise, 10000)
