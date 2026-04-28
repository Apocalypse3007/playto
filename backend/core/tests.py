import threading
from django.test import TransactionTestCase
from django.db import connection, transaction
from rest_framework.test import APIClient
from django.urls import reverse
from uuid import uuid4

from core.models import Merchant, Transaction as LedgerTransaction, Payout, IdempotencyKey
from core.services import request_payout, InsufficientFundsError

class ConcurrencyAndIdempotencyTests(TransactionTestCase):
    # We use TransactionTestCase instead of TestCase because we are testing concurrency and select_for_update,
    # which requires actual database transaction boundaries instead of everything running in one big transaction.
    
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
        A merchant with 100 rupees submits two simultaneous 60 rupee requests. 
        Exactly one should succeed. The other must be rejected cleanly.
        """
        errors = []
        payouts = []
        
        # We need two separate DB connections to simulate true concurrency in threads
        def attempt_payout():
            try:
                # We need to ensure each thread gets its own db connection 
                # in django test environment. TransactionTestCase handles this okay if we close connections.
                payout = request_payout(
                    merchant_id=self.merchant.id,
                    amount_paise=6000, # 60 rupees
                    bank_account_id="BANK_123",
                    idempotency_key=str(uuid4()) # distinct keys so it's not blocked by idempotency lock
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
        
        # Exactly one should have succeeded
        self.assertEqual(len(payouts), 1)
        # Exactly one should have failed with InsufficientFundsError
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], InsufficientFundsError)
        
        # Balance should be 40 rupees (4000 paise)
        self.assertEqual(self.merchant.balance_paise, 4000)

    def test_idempotency_exact_same_response(self):
        """
        The Idempotency-Key header is a merchant-supplied UUID. 
        Second call with the same key returns the exact same response as the first.
        """
        url = reverse('payout_request', kwargs={'merchant_id': self.merchant.id})
        idempotency_key = str(uuid4())
        
        payload = {
            "amount_paise": 1000,
            "bank_account_id": "TEST_ACCT"
        }
        
        # First call
        response1 = self.client.post(url, payload, format='json', headers={'Idempotency-Key': idempotency_key})
        self.assertEqual(response1.status_code, 201)
        
        # Wait a moment
        import time
        time.sleep(0.1)
        
        # Second call with SAME KEY
        response2 = self.client.post(url, payload, format='json', headers={'Idempotency-Key': idempotency_key})
        
        # Status code and body should be exactly the same
        self.assertEqual(response2.status_code, 201)
        self.assertEqual(response1.data, response2.data)
        
        # And verify only ONE payout was created
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(LedgerTransaction.objects.filter(txn_type=LedgerTransaction.Type.PAYOUT_HOLD).count(), 1)
