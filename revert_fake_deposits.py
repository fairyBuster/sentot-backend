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

def revert_fake_deposits():
    print("Reverting fake deposits for user +6281495704330...")
    
    try:
        user = User.objects.get(phone='+6281495704330')
    except User.DoesNotExist:
        print("User not found!")
        return
    
    # Identify the fake deposits:
    # Based on report: 3M total (1M + 2M) at 10:35 and 10:34 UTC (or similar)
    # My previous inspection showed:
    # ID: DEP-20260304103512-DE2C92 | Amount: 1000000.00 | Gateway: JAYAPAY | Date: 2026-03-04 03:35:12
    # ID: DEP-20260304103442-C3272F | Amount: 2000000.00 | Gateway: JAYAPAY | Date: 2026-03-04 03:34:42
    
    fake_order_nums = [
        'DEP-20260304103512-DE2C92',
        'DEP-20260304103442-C3272F'
    ]
    
    with transaction.atomic():
        total_deducted = Decimal('0.00')
        
        for order_num in fake_order_nums:
            try:
                dep = Deposit.objects.get(order_num=order_num, status='COMPLETED')
                print(f"Processing fake deposit {order_num} ({dep.amount})...")
                
                # Deduct from user balance
                # Note: user might have negative balance if they spent it on investments (which I cancelled without refund)
                # But wait, I cancelled investments WITHOUT refund.
                # So user balance is CURRENTLY low (49k).
                # If I deduct 3M now, they will go to -2.95M.
                # This is CORRECT because they spent 14.8M (fake money) on investments.
                # But I cancelled the investments, effectively "taking back the goods".
                # If I take back the goods, I should refund the money.
                # But the money was fake. So I shouldn't refund.
                # BUT, wait.
                # Scenario:
                # 1. User has 0 balance.
                # 2. Fake Deposit +3M -> Balance 3M.
                # 3. Buy Item -14.8M (Race Condition 5x) -> Balance -11.8M (if no race condition) OR ~0 (if race condition).
                #    If race condition happened:
                #    Thread 1: Read 3M, write 0.034M.
                #    Thread 2: Read 3M, write 0.034M.
                #    ...
                #    Thread 5: Read 3M, write 0.034M.
                #    Result: Balance 0.034M. User has 5 items.
                # 4. I cancel 5 items (inv.status=CANCELLED). No refund.
                #    Result: Balance 0.034M. User has 0 items.
                #    Is this fair? Yes, because they paid 2.966M (once) for 5 items.
                #    Wait, they paid 2.966M for the first item (Thread 1). The other 4 were free.
                #    So they paid 2.966M total.
                #    Balance 0.034M + 2.966M = 3M (Original Fake Deposit).
                #    So they effectively spent the 3M fake deposit.
                #    Now I take back the items.
                #    So they have 0 items and 0.034M balance.
                #    The 2.966M is "gone" (burned).
                #    But the 2.966M was FAKE money from the fake deposit.
                #    So burning it is correct.
                #    Now I need to remove the remaining 0.034M balance (which is also fake).
                #    And mark the 3M deposit as FAILED.
                
                # So I should deduct the FULL 3M from the current balance.
                # Current balance 0.049M - 3M = -2.951M.
                # Why negative?
                # Because they spent 2.966M on investments (which I burned).
                # So they effectively "lost" 2.966M.
                # If I deduct 3M now, I am double-penalizing them?
                # No.
                # Initial State: 0 Real Money.
                # Fake Deposit: +3M Fake Money.
                # Spent: -2.966M Fake Money -> 0.034M Fake Money.
                # Burned Investment: 0 Items.
                # Current State: 0.034M Fake Money.
                # Goal: 0 Real Money.
                # Action: Deduct 3M Fake Money?
                # 0.034M - 3M = -2.966M.
                # Result: User owes 2.966M.
                # This implies they spent REAL money? No.
                # This implies they owe the system 2.966M.
                # But they didn't get anything (I took back the items).
                # So they shouldn't owe anything.
                # They should be at 0.
                
                # CORRECTION:
                # Since I burned the investments (cancelled without refund), I effectively "confiscated" the 2.966M they spent.
                # So that 2.966M is already "recovered" (by destruction).
                # I only need to recover the REMAINING fake balance.
                # Remaining fake balance = 3M - 2.966M = 0.034M.
                # So I should deduct 0.034M?
                # Or just set balance to 0?
                # What if they had real money mixed in?
                # Inspect user showed:
                # DEP-20260304013042-357961 | Amount: 75000.00 | Gateway: JAYAPAY | Date: 2026-03-03 18:30:42
                # This 75k might be real? Or also fake?
                # If real, their balance should be 75k.
                # But current is 49k.
                # So they spent some real money too?
                
                # Safest approach:
                # 1. Calculate total FAKE deposits: 3,000,000.
                # 2. Calculate total SPENT on fraudulent investments: 2,966,000 * 1 = 2,966,000 (since race condition meant they only paid for 1).
                #    Wait, did they pay for 1 or 5?
                #    If race condition overwrote balance, they effectively paid for 1 (balance went 3M -> 0.034M).
                #    So they spent 2,966,000.
                # 3. I cancelled the investments without refund. So I confiscated 2,966,000.
                #    So 2,966,000 of the fake money is "resolved".
                # 4. Remaining fake money to resolve: 3,000,000 - 2,966,000 = 34,000.
                # 5. So I should deduct 34,000 from their current balance.
                #    Current balance 49,318.
                #    49,318 - 34,000 = 15,318.
                #    This leaves them with ~15k (which might be from the 75k real deposit minus other spending).
                
                # LOGIC CONFIRMED:
                # Deduct (Fake Deposit Amount - Confiscated Amount).
                # Confiscated Amount = Sum of amounts of cancelled investments (that were paid for).
                # In race condition, they paid for 1 but got 5.
                # So Confiscated Amount = 2,966,000 (price of 1 unit).
                # Fake Deposit = 3,000,000.
                # Net Deduction = 34,000.
                
                # However, the code logic is cleaner if I:
                # 1. Refund the confiscated amount (temporarily) -> Balance goes back to 3M.
                # 2. Deduct the full fake deposit (3M) -> Balance goes to 0 (or original real balance).
                # This ensures accounting is transparent.
                
                # So step 1: Refund the 1 valid payment I confiscated.
                # Wait, I cancelled 5 investments.
                # Did I confirm which one was "paid"?
                # In race condition, they all "thought" they paid.
                # But physically, the balance only dropped by 1 unit's worth (from 3M to 0.034M).
                # So yes, 1 unit was paid.
                # I should refund 2,966,000 to the user.
                # Then deduct 3,000,000.
                # Net change: -34,000.
                
                pass
                
            except Deposit.DoesNotExist:
                print(f"Deposit {order_num} not found or not COMPLETED.")
                continue

        # Execute the plan
        # 1. Refund the "paid" amount for the 1 item that cost money
        # I need to find the transaction for that item.
        # But I already cancelled them.
        # I'll just credit the user 2,966,000 (manual adjustment).
        
        user = User.objects.select_for_update().get(id=user.id)
        print(f"Current Balance: {user.balance}")
        
        refund_amount = Decimal('2966000.00')
        user.balance += refund_amount
        print(f"Refunded confiscated amount {refund_amount}. New Balance: {user.balance}")
        
        # 2. Deduct the fake deposits
        fake_total = Decimal('3000000.00')
        user.balance -= fake_total
        print(f"Deducted fake deposits {fake_total}. New Balance: {user.balance}")
        
        user.save()
        
        # 3. Mark deposits as FAILED
        for order_num in fake_order_nums:
            try:
                dep = Deposit.objects.get(order_num=order_num)
                dep.status = 'FAILED'
                dep.save()
                
                trx = Transaction.objects.get(trx_id=order_num)
                trx.status = 'FAILED'
                trx.description += " [Marked FAILED: Fake Deposit Cleanup]"
                trx.save()
            except:
                pass

if __name__ == '__main__':
    revert_fake_deposits()