# Playto Payout Engine Explainer

## 1. The Ledger
**Query:**
```python
@property
def balance_paise(self):
    total = self.transactions.aggregate(total=Sum('amount_paise'))['total']
    return total or 0
```
This is called to dynamically fetch the merchant's balance based on `Transaction` objects.
**Why Model Credits and Debits this way?**
Modeling financial data with an append-only ledger (`Transaction` log) is the most reliable way to maintain data integrity. Instead of modifying a `balance` column on the `Merchant` (which can fall victim to race conditions or silent computation errors), the current balance is strictly the sum of all historic increments and decrements. Credits are stored as positive integers, while payout holds are stored as negative integers. This ensures the invariant "sum of credits minus debits equals displayed balance" is structurally guaranteed by the database.

## 2. The Lock
**Code:**
```python
@transaction.atomic
def request_payout(merchant_id, amount_paise, bank_account_id, idempotency_key):
    # 1. Lock the merchant row so nobody else can touch their balance
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
    
    # 2. Calculate balance dynamically
    total_db = Transaction.objects.filter(merchant=merchant).aggregate(total=Sum('amount_paise'))['total'] or 0
    
    if total_db < amount_paise:
        raise InsufficientFundsError("Insufficient balance for payout")
    # ... Create Payout, Create Transaction, Return
```
**Database Primitive:** 
It relies on PostgreSQL's row-level locking mechanism, specifically `SELECT ... FOR UPDATE`. When one transaction runs `select_for_update()`, any concurrent request attempting to access that exact `Merchant` row will physically block and wait for the first transaction to `COMMIT` or `ROLLBACK`. This prevents the "Check-then-Deduct" race condition where both requests see a balance of 100, pass the check, and deduct 60 each. By serializing access at the database level, the second request reads the freshly updated ledger state.

## 3. The Idempotency
**How the system knows it has seen a key:**
Whenever the `/api/v1/payouts` is hit, it attempts to `get_or_create` a row in the `IdempotencyKey` table with a `unique_together` constraint on `(key, merchant_id)`.
**What happens if the first request is in-flight when the second arrives?**
The code wraps the idempotency check in a `transaction.atomic()` block and uses `select_for_update()`.
```python
idem_record, created = IdempotencyKey.objects.select_for_update().get_or_create(key=idemp_key, merchant=merchant)
```
If Request 1 is still processing (it created the row but the view hasn't responded), its block is uncommitted. If Request 2 arrives and attempts to select or create that same key, `select_for_update()` will **block** Request 2 until Request 1 finishes its block. Once Request 1 releases its lock, Request 2 queries the row, sees that `created=False` and that `response_body` is either fulfilled (returning the old response) or `None`. If it's `None` (because the payout process happens after the first lock), the API recognizes it's an in-flight duplicate and safely raises a `409 Conflict: Request already in progress`.

## 4. The State Machine
**Where is failed-to-completed blocked?**
Inside `core/services.py`, `transition_payout_state` strictly defines legal target states based on the current state in a dictionary whitelist:
```python
valid_transitions = {
    Payout.State.PENDING: [Payout.State.PROCESSING],
    Payout.State.PROCESSING: [Payout.State.COMPLETED, Payout.State.FAILED],
    Payout.State.COMPLETED: [],
    Payout.State.FAILED: []
}

if target_state not in valid_transitions[current_state]:
    raise InvalidStateTransitionError(f"Cannot transition from {current_state} to {target_state}")
```
As shown, `Payout.State.FAILED` maps to an empty list `[]`, meaning no outgoing transitions are permitted. A failed-to-completed transition evaluates `valid_transitions[Payout.State.FAILED]` and cleanly raises the `InvalidStateTransitionError`.

## 5. The AI Audit
**AI Mistake:** Initially, the AI generated the `Idempotency` check pattern as a simple `IdempotencyKey.objects.filter(key=key).exists()`, followed by logic to create the payout, and then finally create the key.
**What I caught:** I noticed this left a massive race condition. If two requests arrived milliseconds apart, both would see `.exists() == False` because neither had reached the save block yet. 
**What I replaced it with:** I rewrote the block to leverage the atomicity of `.get_or_create()` linked with PostgreSQL's `unique_together` constraints, and moved the `response_body` update to the *end* of the view logic. To properly handle the "first in flight" edge case requested in the specifications, I also injected `select_for_update()` into the `get_or_create` chaining structure so that the database strictly serializes incoming keys.

**Recent AI Audit Additions:**
1. **Retry Logic Bug:** The `retry_stuck_payouts` cron job correctly identified stuck payouts, but it mistakenly re-dispatched the `process_payout` task. Since `process_payout` forces a transition from `PENDING` to `PROCESSING`, and the stuck payouts were *already* in `PROCESSING`, this triggered an `InvalidStateTransitionError` that silently crashed every retry. 
   * **The Fix:** I split the logic by extracting the shared `_simulate_settlement` simulation, and created a dedicated `retry_payout` task that bypasses the initial `PENDING` state check.
2. **Idempotency Race Window:** The response body was being saved *outside* of the `transaction.atomic()` block. This left a tiny race window where a concurrent duplicate request waiting for the lock could wake up, see `response_body=None`, and incorrectly return a `409 Conflict` instead of the proper replayed response.
   * **The Fix:** I updated the logic to call `idem_record.refresh_from_db()` inside the `else` branch right after the lock releases, successfully closing the race condition window.
