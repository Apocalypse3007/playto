# Playto Payout Engine

A scalable, concurrent, and idempotent payout engine simulation resolving "Check-then-Deduct" race conditions, implementing aggressive backoff polling, and ensuring strict atomicity.

## Prerequisites
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