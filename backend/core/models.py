from django.db import models
from django.db.models import Sum
from uuid import uuid4

class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def balance_paise(self):
        # The sum of credits minus debits must always equal the displayed balance.
        # Credit amounts are positive, debit/hold amounts are negative.
        total = self.transactions.aggregate(total=Sum('amount_paise'))['total']
        return total or 0

class Transaction(models.Model):
    class Type(models.TextChoices):
        CREDIT = 'CREDIT', 'Credit'
        DEBIT = 'DEBIT', 'Debit'
        PAYOUT_HOLD = 'PAYOUT_HOLD', 'Payout Hold'
        PAYOUT_REFUND = 'PAYOUT_REFUND', 'Payout Refund'

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='transactions')
    amount_paise = models.BigIntegerField() # No FloatField
    txn_type = models.CharField(max_length=20, choices=Type.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    payout = models.ForeignKey('Payout', on_delete=models.CASCADE, null=True, blank=True, related_name='related_transactions')

class Payout(models.Model):
    class State(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='payouts')
    amount_paise = models.BigIntegerField()
    bank_account_id = models.CharField(max_length=255)
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    retry_count = models.IntegerField(default=0)
    idempotency_key_ref = models.CharField(max_length=255, null=True, blank=True)

class IdempotencyKey(models.Model):
    key = models.CharField(max_length=255)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    response_body = models.JSONField(null=True)
    response_status = models.IntegerField(null=True)
    payout_id = models.UUIDField(null=True) # Useful if we need point back to payout

    class Meta:
        unique_together = ('key', 'merchant')
