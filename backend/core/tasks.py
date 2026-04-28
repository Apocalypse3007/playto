import random
import time
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Payout
from .services import transition_payout_state, InvalidStateTransitionError


@shared_task
def process_payout(payout_id):
    """
    Simulates bank settlement workflow.
    Called for fresh payouts (state = PENDING → PROCESSING → outcome).
    """
    try:
        # Step 1: Move PENDING → PROCESSING
        transition_payout_state(payout_id, Payout.State.PROCESSING)
    except InvalidStateTransitionError:
        # Already moved out of PENDING (e.g. manually settled or duplicate task).
        # Nothing to do.
        return f"Payout {payout_id} already past PENDING, skipping"

    _simulate_settlement(payout_id)


@shared_task
def retry_payout(payout_id):
    """
    Called by retry_stuck_payouts for payouts already stuck in PROCESSING.
    Skips the PENDING→PROCESSING transition (already done) and re-simulates outcome.
    """
    _simulate_settlement(payout_id)


def _simulate_settlement(payout_id):
    """
    Shared settlement simulation: randomly succeeds, fails, or hangs.
    Assumes the payout is already in PROCESSING state.
    """
    outcome = random.choices(
        ['success', 'fail', 'hang'],
        weights=[0.70, 0.20, 0.10],
        k=1
    )[0]

    if outcome == 'hang':
        # Simulate the bank hanging/timing out.
        # Leave the record in PROCESSING so retry_stuck_payouts picks it up.
        return f"Payout {payout_id} hung"

    time.sleep(random.uniform(0.5, 2.0))  # Simulate network delay

    if outcome == 'success':
        try:
            transition_payout_state(payout_id, Payout.State.COMPLETED)
        except InvalidStateTransitionError:
            pass  # Already completed/failed by another path (e.g. manual clear)
        return f"Payout {payout_id} succeeded"

    if outcome == 'fail':
        try:
            transition_payout_state(payout_id, Payout.State.FAILED)
        except InvalidStateTransitionError:
            pass  # Already resolved
        return f"Payout {payout_id} failed"


@shared_task
def retry_stuck_payouts():
    """
    Cron job task to find payouts stuck in PROCESSING > 30s.
    If retry_count < 3, requeue via retry_payout (NOT process_payout).
    If retry_count >= 3, fail and atomically return funds.
    """
    cutoff = timezone.now() - timedelta(seconds=30)
    stuck_payouts = Payout.objects.filter(
        state=Payout.State.PROCESSING,
        updated_at__lt=cutoff
    )

    for payout in stuck_payouts:
        if payout.retry_count >= 3:
            # Max retries exhausted — fail and return funds atomically
            try:
                transition_payout_state(payout.id, Payout.State.FAILED)
            except InvalidStateTransitionError:
                pass  # Already resolved by concurrent process
        else:
            # Increment retry count and requeue with exponential backoff
            payout.retry_count += 1
            payout.save(update_fields=['retry_count'])
            # Use retry_payout, NOT process_payout — payout is already PROCESSING
            retry_payout.apply_async(
                (str(payout.id),),
                countdown=2 ** payout.retry_count  # 2s, 4s, 8s
            )
