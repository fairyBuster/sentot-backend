import os
import django
import sys
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from products.models import Investment, Transaction, Product
from deposits.models import Deposit
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

def cleanup_fraud():
    print("Starting fraud cleanup for user +6281495704330...")
    
    try:
        user = User.objects.get(phone='+6281495704330')
    except User.DoesNotExist:
        print("User +6281495704330 not found!")
        return

    print(f"User found: {user.phone} (ID: {user.id})")
    
    # 1. Find the fraudulent deposit
    # Look for deposits that are COMPLETED but might be suspicious (e.g., recent large deposits)
    deposits = Deposit.objects.filter(user=user, status='COMPLETED').order_by('-created_at')
    
    print("\nRecent Deposits:")
    target_deposit = None
    for dep in deposits[:5]:
        print(f"  {dep.order_num}: {dep.amount} ({dep.created_at})")
        # Assuming the large amount for Padang Lamun purchase
        # 5x purchase of 2,966,000 = 14,830,000. So deposit must be around that.
        if dep.amount > 10000000:
            target_deposit = dep
            
    if not target_deposit:
        print("Could not automatically identify the large deposit. Please check manually.")
        # Fallback: check transactions directly
        trxs = Transaction.objects.filter(user=user, type='DEPOSIT', status='COMPLETED').order_by('-created_at')
        for t in trxs[:5]:
             print(f"  TRX {t.trx_id}: {t.amount}")
             if t.amount > 10000000:
                 # Found it via transaction
                 target_deposit = Deposit.objects.filter(order_num=t.trx_id).first()
                 break
    
    if target_deposit:
        print(f"\nIdentified Fraudulent Deposit: {target_deposit.order_num} ({target_deposit.amount})")
        
        with transaction.atomic():
            # Revert balance
            user = User.objects.select_for_update().get(id=user.id)
            wallet_field = 'balance' if target_deposit.wallet_type == 'BALANCE' else 'balance_deposit'
            current_bal = getattr(user, wallet_field)
            
            # Check if balance is enough to deduct
            if current_bal < target_deposit.amount:
                print(f"WARNING: User balance ({current_bal}) is less than deposit amount ({target_deposit.amount}). User might have spent it.")
                # We will deduct anyway, allowing negative balance or partial deduction?
                # Better to deduct fully to reflect debt
            
            setattr(user, wallet_field, current_bal - target_deposit.amount)
            user.save()
            print(f"  Deducted {target_deposit.amount} from {wallet_field}. New balance: {getattr(user, wallet_field)}")
            
            # Mark deposit and transaction as FAILED (or CANCELLED)
            target_deposit.status = 'FAILED'
            target_deposit.save()
            
            trx = Transaction.objects.get(trx_id=target_deposit.order_num)
            trx.status = 'FAILED'
            trx.description += " [Marked as Fraud/Failed by System]"
            trx.save()
            print("  Marked deposit as FAILED.")

    # 2. Cancel the investments made with this money
    # "Proyek Konservasi-Padang Lamun"
    print("\nCancelling Fraudulent Investments...")
    investments = Investment.objects.filter(
        user=user, 
        product__name__contains="Padang Lamun", 
        status='ACTIVE'
    )
    
    for inv in investments:
        print(f"  Cancelling Investment ID {inv.id} ({inv.product.name})...")
        
        with transaction.atomic():
            inv.status = 'CANCELLED'
            inv.save()
            
            # Cancel transaction
            if inv.transaction:
                inv.transaction.status = 'CANCELLED'
                inv.transaction.description += " [Cancelled: Fraudulent Source]"
                inv.transaction.save()
                
                # Refund? NO. The money was fake.
                # Do NOT refund to balance.
                
                # Revert commissions
                commissions = Transaction.objects.filter(
                    related_transaction=inv.transaction, 
                    type='PURCHASE_COMMISSION',
                    status='COMPLETED'
                )
                
                for comm in commissions:
                    upline = comm.user
                    # Lock upline
                    upline = User.objects.select_for_update().get(id=upline.id)
                    
                    print(f"    Reverting commission {comm.amount} from upline {upline.phone}...")
                    upline.balance -= comm.amount
                    upline.save()
                    
                    comm.status = 'CANCELLED'
                    comm.description += " [Reverted: Fraud source]"
                    comm.save()

    print("\nCleanup complete.")

if __name__ == '__main__':
    cleanup_fraud()