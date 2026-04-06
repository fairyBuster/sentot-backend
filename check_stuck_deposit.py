import os
import django
import sys
import logging
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from products.models import Transaction
from deposits.models import Deposit, GatewaySettings
from django.contrib.auth import get_user_model
from deposits.utils import check_jayapay_status

User = get_user_model()

def check_stuck_deposit():
    order_num = "DEP-20260304110040-E8340A"
    print(f"Checking Deposit {order_num}...")
    
    try:
        dep = Deposit.objects.get(order_num=order_num)
        print(f"Status: {dep.status}")
        print(f"Amount: {dep.amount}")
        print(f"User: {dep.user.phone}")
        print(f"Transaction Status: {dep.transaction.status if dep.transaction else 'No Trx'}")
        print(f"Transaction Description: {dep.transaction.description if dep.transaction else ''}")
        print(f"Callback Payload: {dep.callback_payload}")
    except Deposit.DoesNotExist:
        print("Deposit not found!")
        return

    # Check why it might have failed
    # We can try to manually run the inquiry check to see what Jayapay returns now
    gs = GatewaySettings.objects.order_by('-updated_at').first()
    merchant_code = (gs.jayapay_merchant_code or '').strip() if gs else ''
    private_key = (gs.jayapay_private_key or '').strip() if gs else ''
    
    if not merchant_code or not private_key:
        print("Gateway settings missing!")
        return
        
    print("\nRunning Inquiry Check manually...")
    is_valid = check_jayapay_status(order_num, merchant_code, private_key)
    print(f"Inquiry Result: {is_valid}")
    
    if is_valid and dep.status != 'COMPLETED':
        print("INCONSISTENCY FOUND: Inquiry says SUCCESS but local status is not COMPLETED.")
        # This confirms the issue might be temporary network failure during callback or logic bug
    elif not is_valid:
        print("Inquiry returned FALSE/FAILED. This explains why it was rejected.")

if __name__ == '__main__':
    check_stuck_deposit()