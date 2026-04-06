import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from products.models import Investment, Transaction
from deposits.models import Deposit
from django.contrib.auth import get_user_model

User = get_user_model()

def inspect_user():
    print("Inspecting user +6281495704330...")
    
    try:
        user = User.objects.get(phone='+6281495704330')
    except User.DoesNotExist:
        print("User not found!")
        return

    print(f"User: {user.phone}")
    print(f"Current Balance: {user.balance}")
    print(f"Current Deposit Balance: {user.balance_deposit}")
    
    print("\n--- Completed Deposits (Last 20) ---")
    deposits = Deposit.objects.filter(user=user, status='COMPLETED').order_by('-created_at')[:20]
    for dep in deposits:
        print(f"ID: {dep.order_num} | Amount: {dep.amount} | Gateway: {dep.gateway} | Date: {dep.created_at}")
        
    print("\n--- Recent Transactions (Last 20) ---")
    trxs = Transaction.objects.filter(user=user).order_by('-created_at')[:20]
    for t in trxs:
        print(f"Trx: {t.trx_id} | Type: {t.type} | Amount: {t.amount} | Status: {t.status}")

if __name__ == '__main__':
    inspect_user()