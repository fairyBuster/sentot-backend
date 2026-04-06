import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from products.models import Transaction
from deposits.models import Deposit
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

def fix_stuck_deposits():
    # List of deposits reported as stuck
    stuck_orders = [
        'DEP-20260304110040-E8340A', # The one with callback payload provided
        'DEP-20260304110221-0BD5D4', # The new one user complained about
    ]
    
    print("Fixing stuck deposits manually...")
    
    for order_num in stuck_orders:
        try:
            dep = Deposit.objects.get(order_num=order_num)
        except Deposit.DoesNotExist:
            print(f"Deposit {order_num} not found.")
            continue
            
        print(f"\nProcessing {order_num} ({dep.amount})...")
        print(f"  Current Status: {dep.status}")
        
        if dep.status == 'COMPLETED':
            print("  Already COMPLETED. Skipping.")
            continue
            
        # Manually credit the user
        with transaction.atomic():
            user = dep.user
            # Lock user
            user = User.objects.select_for_update().get(id=user.id)
            
            print(f"  User: {user.phone}")
            print(f"  Old Balance: {user.balance}")
            
            user.balance += dep.amount
            user.save()
            
            print(f"  New Balance: {user.balance}")
            
            # Update Deposit
            dep.status = 'COMPLETED'
            dep.save()
            
            # Update Transaction
            if dep.transaction:
                dep.transaction.status = 'COMPLETED'
                dep.transaction.description += " [Manual Fix: Callback Logic Updated]"
                dep.transaction.save()
                
            print("  Marked as COMPLETED.")

if __name__ == '__main__':
    fix_stuck_deposits()