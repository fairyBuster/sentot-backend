import os
import django
import sys
import logging
import requests
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from products.models import Transaction
from deposits.models import Deposit, GatewaySettings
from django.contrib.auth import get_user_model
from withdrawal.integrations.jayapay import sign_params_legacy

User = get_user_model()

def brute_force_inquiry():
    order_num = "DEP-20260304110040-E8340A"
    print(f"Brute-forcing Inquiry URLs for {order_num}...")
    
    gs = GatewaySettings.objects.order_by('-updated_at').first()
    merchant_code = (gs.jayapay_merchant_code or '').strip() if gs else ''
    private_key = (gs.jayapay_private_key or '').strip() if gs else ''
    
    if not merchant_code or not private_key:
        print("Gateway settings missing!")
        return

    params = {
        "merchantCode": merchant_code,
        "orderNum": order_num,
    }
    
    sign = sign_params_legacy(params, private_key)
    params["sign"] = sign
    
    base_url = "https://openapi.jayapayment.com"
    paths = [
        "/gateway/queryOrder",
        "/gateway/orderQuery",
        "/gateway/query",
        "/gateway/checkOrder",
        "/gateway/orderCheck",
        "/gateway/prepaidOrderQuery",
        "/gateway/cash/query", # Maybe cash path?
        "/queryOrder",
        "/orderQuery",
        "/api/gateway/queryOrder",
    ]
    
    for path in paths:
        url = base_url + path
        print(f"Trying {url}...")
        try:
            resp = requests.post(url, json=params, timeout=10)
            print(f"  Status: {resp.status_code}")
            if resp.status_code != 404:
                print(f"  Response: {resp.text[:200]}")
                if resp.status_code == 200:
                    print("  !!! POTENTIAL MATCH !!!")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == '__main__':
    brute_force_inquiry()