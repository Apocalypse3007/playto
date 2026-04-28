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
    merchant = Merchant.objects.get(id=merchant_id)
        
    # 1. Create the pending payout
    payout = Payout.objects.create(
        merchant=merchant,
        amount_paise=amount_paise,
        bank_account_id=bank_account_id,
        state=Payout.State.PENDING,
        idempotency_key_ref=idempotency_key
    )
    
    # Do not hold funds, as this is a request for funds.
    
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
    
    # If failing, no refund is needed because no funds were held at request time.
    if target_state == Payout.State.FAILED:
        pass
        
    # If completing, credit the requester and debit the payer.
    if target_state == Payout.State.COMPLETED:
        # Credit the requester (the one who asked for money)
        Transaction.objects.create(
            merchant=payout.merchant,
            amount_paise=payout.amount_paise,
            txn_type=Transaction.Type.CREDIT,
            payout=payout
        )
        
        # Debit the payer (the person who was asked for money)
        import uuid
        try:
            uuid_val = uuid.UUID(payout.bank_account_id)
            payer = Merchant.objects.filter(id=uuid_val).first()
            if payer:
                Transaction.objects.create(
                    merchant=payer,
                    amount_paise=-payout.amount_paise,
                    txn_type=Transaction.Type.DEBIT,
                    payout=payout
                )
        except (ValueError, TypeError):
            # Not a valid UUID, so treat as external bank account payout
            pass
            
    payout.save()
    return payout
