from django.db import transaction
from django.db.models import Sum
from .models import Merchant, Transaction, Payout

class InsufficientFundsError(Exception):
    pass

class InvalidStateTransitionError(Exception):
    pass

@transaction.atomic
def request_payout(merchant_id, amount_paise, bank_account_id, idempotency_key):
    """
    Core function for payout request logic.
    """
    # 1. Lock the merchant row so nobody else can touch their balance
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
        
    # 2. Calculate balance dynamically
    total_db = Transaction.objects.filter(merchant=merchant).aggregate(total=Sum('amount_paise'))['total'] or 0
    
    if total_db < amount_paise:
        raise InsufficientFundsError("Insufficient balance for payout")

    # 3. Create the pending payout
    payout = Payout.objects.create(
        merchant=merchant,
        amount_paise=amount_paise,
        bank_account_id=bank_account_id,
        state=Payout.State.PENDING,
        idempotency_key_ref=idempotency_key
    )
    
    # 4. Hold the funds by creating a PAYOUT_HOLD transaction (negative amount)
    Transaction.objects.create(
        merchant=merchant,
        amount_paise=-amount_paise,
        txn_type=Transaction.Type.PAYOUT_HOLD,
        payout=payout
    )
    
    return payout

@transaction.atomic
def transition_payout_state(payout_id, target_state):
    """
    Move a payout from one state to another, enforcing legal transitions.
    If it fails, we need to return the funds to the ledger.
    """
    payout = Payout.objects.select_for_update().get(id=payout_id)
    current_state = payout.state
    
    # Legal transitions:
    # pending -> processing
    # processing -> completed
    # processing -> failed
    
    valid_transitions = {
        Payout.State.PENDING: [Payout.State.PROCESSING],
        Payout.State.PROCESSING: [Payout.State.COMPLETED, Payout.State.FAILED],
        Payout.State.COMPLETED: [],
        Payout.State.FAILED: []
    }
    
    if target_state not in valid_transitions[current_state]:
        raise InvalidStateTransitionError(f"Cannot transition from {current_state} to {target_state}")
        
    payout.state = target_state
    
    # If failing, refund the held funds.
    if target_state == Payout.State.FAILED:
        Transaction.objects.create(
            merchant=payout.merchant,
            amount_paise=payout.amount_paise,
            txn_type=Transaction.Type.PAYOUT_REFUND,
            payout=payout
        )
        
    # If completing, the funds are already held. We don't need to do anything for the payer except maybe converting the hold to a debit.
    # Actually, the hold is already a negative value, so the balance is correct.
    # We might just add a DEBIT to the payer and a CREDIT to the payer to cancel the hold, but the hold already decremented the balance.
    # Wait, the spec says "debit the payer"?
    # Let's just leave the HOLD as the debit for the payer. It's mathematically the same.
    # However, for the recipient (the bank account id), if it's another merchant, we should credit them.
    if target_state == Payout.State.COMPLETED:
        # Credit the recipient
        import uuid
        try:
            uuid_val = uuid.UUID(payout.bank_account_id)
            recipient = Merchant.objects.filter(id=uuid_val).first()
            if recipient:
                Transaction.objects.create(
                    merchant=recipient,
                    amount_paise=payout.amount_paise,
                    txn_type=Transaction.Type.CREDIT,
                    payout=payout
                )
        except (ValueError, TypeError):
            # Not a valid UUID, so treat as external bank account payout
            pass
            
    payout.save()
    return payout
