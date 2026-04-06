import os
import sys
import subprocess
import django
from datetime import datetime

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from deposits.models import Deposit
from django.utils import timezone

def get_recent_deposits(limit=5):
    return Deposit.objects.all().order_by('-created_at')[:limit]

def get_recent_logs(lines=15):
    try:
        # Fetch logs from journalctl for the ocerbackend service
        # Filter for "deposits", "Jayapay", or "callback"
        # Using journalctl requires root/sudo usually, but here run as root
        cmd = "journalctl -u ocerbackend -n 100 --no-pager | grep -iE 'deposit|jayapay|callback' | tail -n " + str(lines)
        result = subprocess.check_output(cmd, shell=True).decode('utf-8')
        return result
    except Exception:
        return "Could not fetch logs (service might not be running or no permission)."

def show():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"=== DEPOSIT MONITOR [{now}] ===\n")
    
    print("--- LATEST DATABASE ENTRIES ---")
    deposits = get_recent_deposits()
    print(f"{'ORDER NUM':<30} | {'AMOUNT':<12} | {'STATUS':<10} | {'USER':<15} | {'TIME'}")
    print("-" * 90)
    
    for dep in deposits:
        try:
            created_at = dep.created_at.astimezone().strftime('%H:%M:%S')
            user_phone = dep.user.phone if dep.user else 'Unknown'
            print(f"{dep.order_num:<30} | {dep.amount:,.0f}{'':<4} | {dep.status:<10} | {user_phone:<15} | {created_at}")
        except:
            pass
            
    print("\n" + "=" * 90 + "\n")
    
    print("--- REALTIME LOGS (Jayapay/Deposit) ---")
    logs = get_recent_logs()
    if logs.strip():
        print(logs)
    else:
        print("(No recent matching logs found)")

if __name__ == '__main__':
    show()