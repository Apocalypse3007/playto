import os
import django
import sys

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Merchant, Transaction

def seed():
    print("Clearing old data...")
    Merchant.objects.all().delete()
    
    print("Seeding Merchants...")
    m1 = Merchant.objects.create(name="Acme Corp")
    m2 = Merchant.objects.create(name="Globex Inc")
    m3 = Merchant.objects.create(name="Soylent Corp")
    
    print("Seeding Credits...")
    # Acme gets 500.00 INR = 50000 paise
    Transaction.objects.create(merchant=m1, amount_paise=50000, txn_type=Transaction.Type.CREDIT)
    # Globex gets 1250.50 INR = 125050 paise
    Transaction.objects.create(merchant=m2, amount_paise=125050, txn_type=Transaction.Type.CREDIT)
    # Soylent gets 10.00 INR = 1000 paise
    Transaction.objects.create(merchant=m3, amount_paise=1000, txn_type=Transaction.Type.CREDIT)
    
    print("Seed complete!")
    print(f"Merchant 1: {m1.id} | Balance: {m1.balance_paise} paise")
    print(f"Merchant 2: {m2.id} | Balance: {m2.balance_paise} paise")
    print(f"Merchant 3: {m3.id} | Balance: {m3.balance_paise} paise")

if __name__ == '__main__':
    seed()
