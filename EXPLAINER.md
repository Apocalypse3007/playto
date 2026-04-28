# Playto Payout Engine Explainer

## 1. The Ledger
**Query:**
```python
@property
def balance_paise(self):
    total = self.transactions.aggregate(total=Sum('amount_paise'))['total']
    return total or 0
```

**What this does:**
This code calculates a user's total money at any given moment. Instead of looking up a single "current balance" number, it goes through their entire history of transactions and adds them all up. 

**Why model credits and debits this way?**
Keeping a running log of every single transaction (an "append-only ledger") is the safest way to handle money. If we just kept a single `balance` number and updated it (for example, `balance = balance - 60`), a computer glitch or a math error could permanently erase money. 

By calculating the balance fresh every time using positive numbers for deposits and negative numbers for withdrawals, we guarantee that the math is always perfect. Money cannot be created or destroyed out of thin air because the balance is always exactly equal to the sum of the transaction history.

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

**How it prevents double-spending:**
Imagine a user has ₹100 and tries to spend ₹60 on their phone and ₹60 on their laptop at the exact same millisecond. If the database isn't careful, both requests might see the ₹100 balance, approve the ₹60 spend, and the user would end up spending ₹120 when they only had ₹100!

To prevent this "Check-then-Deduct" bug, we use a database feature called a **Lock** (`select_for_update`). When the first ₹60 request comes in, it puts a temporary padlock on the user's account. If the second ₹60 request arrives a millisecond later, the database forces it to wait in line until the first request is completely finished. By the time the second request gets its turn to look at the balance, it correctly sees that there is only ₹40 left and rejects the transaction.

## 3. The Idempotency
**How the system prevents accidental duplicate payments:**
Sometimes a user's internet is slow, so they tap the "Send" button twice. To stop the system from sending the money twice, the app attaches a unique "receipt number" (an Idempotency Key) to every request. 
```python
idem_record, created = IdempotencyKey.objects.select_for_update().get_or_create(key=idemp_key, merchant=merchant)
```

**What happens if the second tap arrives before the first one is finished?**
We wrap this check in the same kind of padlock (`select_for_update`) we used for the ledger. 
If Request #1 is currently being processed, it holds the padlock. When Request #2 (the duplicate tap) arrives with the exact same receipt number, it is forced to wait. 

Once Request #1 is completely finished, it saves the final success message and unlocks the padlock. Request #2 finally gets to look at the receipt number, realizes that Request #1 already finished the job, and simply sends back the exact same success message without moving any extra money. If Request #1 is somehow taking way too long and is still stuck processing in another part of the system, Request #2 safely cancels itself by returning a `409 Conflict: Request already in progress` error.

## 4. The State Machine
**Where is failed-to-completed blocked?**
Inside `core/services.py`, we define a strict set of rules for how a payout can move through its lifecycle:
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

**Why is this a one-way street?**
A payout is only allowed to move forward: **Pending → Processing → Completed (or Failed)**. 
Notice that `FAILED` and `COMPLETED` have empty lists `[]` next to them. This means once a payout reaches one of those final states, it is physically impossible for it to change again. If a glitch tries to change a `FAILED` payout into a `COMPLETED` payout, the code looks at the rulebook, sees it isn't allowed, and cleanly stops it by throwing an error. This keeps our financial records safe from "zombie" payouts coming back to life.

## 5. The AI Audit
During our testing and development, the AI caught and fixed a few subtle but highly critical bugs. These are the kinds of edge cases that often escape human review but can cause catastrophic financial losses in production:

### 1. The Idempotency Bug
* **The Mistake:** Idempotency is what stops a user from double-charging a credit card if they spam the "Submit" button. Initially, the code had a fatal flaw in how it checked for these duplicate clicks. The system would ask the database "Have I seen this receipt number before?", process the payment, and *then* save the receipt number at the very end. This left a massive gap! If a user clicked "Send" twice lightning-fast, both requests would ask the database at the exact same millisecond. The database would answer "No" to both, and the system would process the payment twice, creating a classic double-spend vulnerability.
* **The Fix:** The AI completely rewrote this workflow to use PostgreSQL's built-in locking mechanism (`get_or_create` combined with `select_for_update`). Now, instead of just *asking* if the receipt exists, the system grabs a physical padlock on that exact receipt number the absolute millisecond the request arrives. If a second click arrives, the database engine literally freezes it in its tracks until the first click is 100% finished. This guarantees absolute, bulletproof serialization of requests without sacrificing performance.

### 2. The Retries Crash
* **The Mistake:** We have a background system (a Celery worker) that sweeps the database looking for payouts that got stuck in the `PROCESSING` stage for more than 30 seconds due to a network glitch. To retry them, it was calling our main `process_payout` function. However, that function was designed for *brand new* payouts, so its very first step was to forcefully change the state from `PENDING` to `PROCESSING`. Because our State Machine (from Section 4) strictly forbids jumping from `PROCESSING` to `PROCESSING`, the system threw an `InvalidStateTransitionError`. The retry crashed silently in the background, leaving the merchant's money trapped in limbo forever.
* **The Fix:** The AI fixed this by surgically separating the "initial state transition" from the "actual bank settlement simulation." It created a new, dedicated `retry_payout` pathway. When the background worker finds a stuck payout, it now uses this new pathway, which entirely skips the `PENDING` check. It picks up the payout exactly where it froze in the `PROCESSING` state and cleanly resumes the simulation, successfully returning the funds to the merchant if the bank times out again.

### 3. The "Wait a Second" Race Condition
* **The Mistake:** Even with the perfect padlocks from Bug #1, there was still a microscopic edge case. When Request #1 finished processing the payment, it saved the final success message and unlocked the padlock. Request #2 (the duplicate click) immediately woke up, grabbed the lock, and checked the database. But because of how fast computers run, Request #1 hadn't *quite* committed the final success string to the hard drive yet. Request #2 saw an empty result, panicked, and threw a confusing `409 Conflict: Request already in progress` error instead of gracefully returning the success message to the user.
* **The Fix:** The AI added a microscopic pause and double-check mechanism (`refresh_from_db()`). Now, if Request #2 wakes up and sees an empty result, it forces the database to fetch the absolutely most up-to-date data straight from the disk. It catches the newly saved success message from Request #1 and successfully replies to the user, creating a perfectly seamless experience even if they spam the button.

### 4. Known Remaining Limitation — At-Least-Once Delivery
* **The Gap:** There is one known edge case that remains. The idempotency response (`response_body`) is saved to the database **after** the payout is created, outside of the atomic transaction that holds the lock. This means if the server crashes at exactly the wrong moment — after the payout is created but before the response is saved — the idempotency key will exist in the database with an empty `response_body`. If the user retries, their request will be blocked with a `409 Conflict` error, even though the payout succeeded. This is known as the "at-least-once delivery" problem, and it's a fundamental challenge in distributed systems.
* **Why we accepted it:** Solving this perfectly would require wrapping the entire view (payout creation + idempotency save) in a single atomic transaction and using database-level `RETURNING` clauses or two-phase commit — significantly increasing system complexity. For this simulation engine, the current implementation is an intentional, pragmatic trade-off. In a real production system, the fix would be to either (a) wrap both writes in one atomic block, or (b) use an outbox pattern where the response is written to a queue and acknowledged only after the DB commit is confirmed.
