# Playto Payout Engine

A scalable, concurrent, and idempotent payout engine simulation resolving "Check-then-Deduct" race conditions, implementing aggressive backoff polling, and ensuring strict atomicity.

---

## How It Works

The application is made up of three layers — a **React frontend**, a **Django backend**, and a **PostgreSQL database** — plus a **Celery background worker** for async processing. Here is exactly how a payout flows through all of them:

```
[React Frontend]  →  [Django REST API]  →  [PostgreSQL]
      ↑                     ↓
      └────── polls ──  [Celery Worker]
```

### 1. User Interaction (React Frontend)
The frontend is a single-page React app served by Vite on `http://localhost:5173`. It does two things:
- **Displays the dashboard:** On page load, it calls `GET /api/v1/merchants/<uuid>/dashboard`. Django queries PostgreSQL, sums up all of the merchant's transactions using a single DB aggregation, and returns the current balance, held funds, recent transactions, and payout history as JSON. The frontend renders all of this.
- **Sends payout requests:** When the user fills in an amount and a counterparty UUID and clicks "Request Payout", the frontend sends a `POST /api/v1/merchants/<uuid>/payouts` request with a randomly generated `Idempotency-Key` header. It then polls the dashboard API every few seconds to reflect the latest payout state in real time.

### 2. Business Logic (Django Backend)
Django is the brain of the system. When a payout request arrives it does the following steps in order:
1. **Idempotency check** — It locks the idempotency key row in PostgreSQL (`SELECT FOR UPDATE`) so duplicate requests are stopped at the gate before any money moves.
2. **Balance check** — Inside an `@transaction.atomic` block, it places a database row-level lock on the merchant's account and re-reads the balance fresh from the database using a `SUM()` aggregate. This prevents two simultaneous requests from both seeing the same balance and double-spending.
3. **Ledger write** — If funds are sufficient, it creates a `Payout` record and a corresponding `PAYOUT_HOLD` transaction (a negative amount) in a single atomic write. The merchant's available balance immediately reflects the deduction.
4. **State transitions** — A strict state machine (`PENDING → PROCESSING → COMPLETED/FAILED`) is enforced in `core/services.py`. Any illegal transition (e.g., `FAILED → COMPLETED`) is blocked and raises an error.

### 3. Data Integrity (PostgreSQL)
PostgreSQL is not just storage here — it actively enforces the money rules:
- **Row-level locks** (`SELECT FOR UPDATE`) serialize concurrent payout requests, making race conditions physically impossible at the infrastructure level.
- **Atomic transactions** (`BEGIN / COMMIT / ROLLBACK`) guarantee that a payout hold and a state change either both succeed or both fail together. There is never a "half-written" state.
- **The balance is never stored as a column.** It is always calculated as `SUM(amount_paise)` over the full transaction history, meaning it is always mathematically correct by definition.

### 4. Async Settlement (Celery + Redis)
The Celery worker runs as a separate background process, connected to Django via Redis (the message broker). Its job is to simulate the real-world delay of a bank settlement:
- When a payout is dispatched, Celery picks up the task and simulates a bank response: **70% chance of success**, **20% chance of failure**, **10% chance of a hang**.
- On **success**, the payout is marked `COMPLETED` and the recipient gets a `CREDIT` transaction in their ledger.
- On **failure**, the payout is marked `FAILED` and a `PAYOUT_REFUND` transaction is created *atomically* with the state change, instantly returning the held funds to the sender.
- On a **hang**, the payout stays stuck in `PROCESSING`. A separate cron job (`retry_stuck_payouts`) finds it after 30 seconds and retries with exponential backoff (2s, 4s, 8s), failing it permanently after 3 attempts.

> **Note:** In the current UI simulation, payouts go through a manual two-step approval flow (sender clicks "Settle", receiver clicks "Clear Due") rather than being auto-dispatched to the Celery worker. The full async worker infrastructure is wired up and ready for the automated flow.

---

- **Docker** and **Docker Compose** (for PostgreSQL and Redis)
- **Node.js** (for Vite React frontend)
- **Python 3.10+** (for Django DRF backend)

---

## 1. Start the Databases
The application relies on PostgreSQL to enforce row-level locking for money integrity, and Redis as the Celery message broker.

```powershell
cd /path/to/playto
docker-compose up -d
```
> Wait a few seconds for the PostgreSQL container to initialize on port 5432 and Redis on 6379.

---

## 2. Setup the Django Backend
Open a **new terminal window** and navigate into the `backend` folder.

```powershell
cd backend
# 1. Activate the Virtual Environment
.\venv\Scripts\activate

# 2. Apply Database Migrations (creates Ledger, Merchants, Idempotency tables)
python manage.py makemigrations core api
python manage.py migrate

# 3. Seed Initial Data
# This seeds 3 merchants and starts them with simulated credits (e.g., 500 INR, 1250 INR...)
python seed.py
# ! IMPORTANT: Note down one of the Merchant UUIDs printed in the terminal. You will need it to login to the frontend.

# 4. Start the API Server
python manage.py runserver
```
> The Django backend should now be listening at `http://localhost:8000`.

---

## 3. Start the Background Workers (Celery)
Because we are processing payouts asynchronously, we need to spin up Celery.

Open a **new terminal window** in the `backend` folder:
```powershell
.\venv\Scripts\activate
# Start the worker process to handle simulated banking (Success/Fail/Hang)
# Note: On Windows, "-P gevent" or "-P solo" is required for Celery
pip install gevent
celery -A config worker --loglevel=info -P gevent
```

*(Optional Retry Job)* Open another terminal to start the Celery Beat scheduler that requeues stuck payouts:
```powershell
.\venv\Scripts\activate
celery -A config beat --loglevel=info
```

---

## 4. Start the React Frontend
Open a **new terminal window** and navigate to the `frontend` folder.

```powershell
cd frontend

# 1. Install Dependencies
npm install

# 2. Run the Vite development server
npm run dev
```

> Open your browser to `http://localhost:5173`. 
> You will be prompted to enter a **Merchant UUID**. Paste the ID you noted from the `python seed.py` output to view their ledger dashboard and submit payouts!

---

## Testing Run-book
To run the concurrency and idempotency tests:
```powershell
cd backend
.\venv\Scripts\activate
python manage.py test core
```
These tests utilize Python threading streams testing database `.select_for_update()` transaction blocks to guarantee zero money integrity leaks during concurrent payouts.



Globex: 6c773ab6-7fa7-41c7-bd5d-023565422a3b
Acme: 357a272b-3adb-4a90-a0af-a4453bae8612
Soylent: bea8accb-366a-407c-8859-9c5728b809b2