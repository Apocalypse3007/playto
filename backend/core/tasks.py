import random
import time
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Payout
from .services import transition_payout_state

@shared_task
def process_payout(payout_id):
    """
    Simulates bank settlement workflow.
    - Moves payout to PROCESSING.
    - Hangs, succeeds, or fails based on probability.
    """
    # Force state transition to processing
    transition_payout_state(payout_id, Payout.State.PROCESSING)
    
    # Simulate randomness
    outcome = random.choices(
        ['success', 'fail', 'hang'],
        weights=[0.70, 0.20, 0.10],
        k=1
    )[0]
    
    if outcome == 'hang':
        # Simulate the bank hanging/timing out. We do nothing, 
        # leaving the record stuck in PROCESSING so the retry task picks it up later.
        return f"Payout {payout_id} hung"
        
    time.sleep(random.uniform(0.5, 2.0)) # Simulate network delay
    
    if outcome == 'success':
        transition_payout_state(payout_id, Payout.State.COMPLETED)
        return f"Payout {payout_id} succeeded"
        
    if outcome == 'fail':
        transition_payout_state(payout_id, Payout.State.FAILED)
        return f"Payout {payout_id} failed"

@shared_task
def retry_stuck_payouts():
    """
    Cron job task to find payouts stuck in processing > 30s.
    If retry_count < 3, requeue for processing.
    If retry_count >= 3, fail and return funds.
    """
    cutoff = timezone.now() - timedelta(seconds=30)
    stuck_payouts = Payout.objects.filter(state=Payout.State.PROCESSING, updated_at__lt=cutoff)
    
    for payout in stuck_payouts:
        if payout.retry_count >= 3:
            # Reached max retries, mark as failed outright
            transition_payout_state(payout.id, Payout.State.FAILED)
        else:
            # Increment retry count and requeue task
            payout.retry_count += 1
            payout.save(update_fields=['retry_count'])
            # We skip 'transition_payout_state' to PROCESSING because it's already there and we don't want to reset it
            process_payout.apply_async((str(payout.id),), countdown=2 ** payout.retry_count) # exp backoff
