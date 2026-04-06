import os
import django
import sys
import uuid
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from products.models import Product, Investment, Transaction
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

User = get_user_model()

def fix_duplicates():
    print("Starting duplicate analysis and cleanup...")
    print("----------------------------------------")
    
    # 1. Find users with duplicate investments exceeding limit
    products = Product.objects.all()
    
    found_issues = False
    
    for product in products:
        limit = product.purchase_limit
        if limit < 1:
            limit = 1 # Safety
            
        # Get users who have more active investments than purchase_limit
        investments = Investment.objects.filter(product=product, status='ACTIVE')
        user_counts = investments.values('user').annotate(count=Count('id')).filter(count__gt=limit)
        
        for entry in user_counts:
            found_issues = True
            user_id = entry['user']
            count = entry['count']
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                continue
                
            print(f"\n[ALERT] User {user.phone} (ID: {user.id}) has {count} active investments for '{product.name}' (Limit: {limit})")
            
            # Get all active investments for this user and product, ordered by creation time
            # We use created_at to determine which one is "original" and which are "duplicates"
            user_investments = list(Investment.objects.filter(
                user=user, 
                product=product, 
                status='ACTIVE'
            ).order_by('created_at', 'id'))
            
            # Keep the first 'limit' investments
            to_keep = user_investments[:limit]
            to_cancel = user_investments[limit:]
            
            print(f" -> Keeping IDs: {[i.id for i in to_keep]}")
            print(f" -> Cancelling IDs: {[i.id for i in to_cancel]}")
            
            with transaction.atomic():
                for inv in to_cancel:
                    print(f"    Processing cleanup for Investment ID {inv.id}...")
                    
                    # 1. Refund the money
                    refund_amount = inv.total_amount
                    
                    # Check which wallet was used
                    wallet_type = 'BALANCE'
                    if inv.transaction:
                        wallet_type = inv.transaction.wallet_type
                    else:
                        wallet_type = 'BALANCE' if product.balance_source == 'balance' else 'BALANCE_DEPOSIT'
                    
                    # Update user balance
                    # Lock user row
                    user = User.objects.select_for_update().get(id=user_id)
                    
                    if wallet_type == 'BALANCE':
                        old_bal = user.balance
                        user.balance += refund_amount
                        print(f"    Refunding {refund_amount} to BALANCE. {old_bal} -> {user.balance}")
                    else: # BALANCE_DEPOSIT
                        old_bal = user.balance_deposit
                        user.balance_deposit += refund_amount
                        print(f"    Refunding {refund_amount} to BALANCE_DEPOSIT. {old_bal} -> {user.balance_deposit}")
                    user.save()
                    
                    # 2. Update Investment status
                    inv.status = 'CANCELLED'
                    inv.save()
                    
                    # 3. Update Transaction status
                    related_trx = inv.transaction
                    if related_trx:
                        related_trx.status = 'CANCELLED'
                        related_trx.description += ' [Auto-cancelled due to duplicate/spam]'
                        related_trx.save()
                        
                        # 4. Create Refund Transaction
                        refund_trx = Transaction.objects.create(
                            user=user,
                            product=product,
                            type='RETURN', # Using RETURN as discussed
                            amount=refund_amount,
                            description=f'Refund for duplicate investment {inv.id} (Spam cleanup)',
                            status='COMPLETED',
                            wallet_type=wallet_type,
                            related_transaction=related_trx,
                            trx_id=f'REF-{inv.id}-{uuid.uuid4().hex[:6].upper()}'
                        )
                        print(f"    Created refund transaction {refund_trx.trx_id}")
                        
                        # 5. Revert Commissions
                        commissions = Transaction.objects.filter(related_transaction=related_trx, type='PURCHASE_COMMISSION')
                        for comm in commissions:
                            if comm.status == 'COMPLETED':
                                upline = comm.user
                                # Lock upline
                                upline = User.objects.select_for_update().get(id=upline.id)
                                
                                old_upline_bal = upline.balance
                                upline.balance -= comm.amount
                                upline.save()
                                
                                comm.status = 'CANCELLED'
                                comm.description += ' [Reverted due to spam refund]'
                                comm.save()
                                print(f"    Reverted commission {comm.amount} for upline {upline.phone}. {old_upline_bal} -> {upline.balance}")

    if not found_issues:
        print("\nNo duplicate investments found exceeding limits.")
    else:
        print("\nCleanup completed successfully.")

if __name__ == '__main__':
    fix_duplicates()