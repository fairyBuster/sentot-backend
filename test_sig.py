import os
import django
import sys
import json
import logging

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from deposits.models import GatewaySettings
from deposits.utils import verify_jayapay_signature

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

def test_sig():
    payload_str = '{"msg":"SUCCESS","code":"00","method":"QRIS","orderNum":"DEP-20260304110040-E8340A","platOrderNum":"PT1C289D118D00604F","payFee":"68400","payMoney":"1520000","name":"usermm963svk5483","platSign":"QjoVHFe7AqUkw6s5YhcSnYu/+uwsFy+SxOFPPLD1aXKhdaxWoMnCJ0x1tR/WnkrtA7yTK3xsL/lxmhKzyOhRPWABU9hj0oGGypaP6DxGOb5JRRCk8BuZqXPfviXIFdnpdkmN8K7Mu+qPAvzNrpDLt+FLpLOxlor/+WK3ECx6gYGITN88Ue0te5su7+9WGRGwjiPZrkb+PoLgsIqqD3Dexn1Yu5P951VPM9b1pcTyazsk5mhbOhAZ/kZSBN0ys9Om+o52js8vT7OlKg5oChKoF67eZjhya/e4+LbRg/Ve70zz8qNODETdXdRxvFm3lekUCRzQxuuavVS7OuhWyo9nYA==","email":"user_mm963svk_2w1i7a@example.com","status":"SUCCESS"}'
    
    data = json.loads(payload_str)
    
    gs = GatewaySettings.objects.order_by('-updated_at').first()
    pk = gs.jayapay_public_key
    
    print("Testing Signature Verification...")
    print(f"Public Key (First 30 chars): {pk[:30]}")
    
    result = verify_jayapay_signature(data, pk)
    print(f"Result: {result}")
    
    if result:
        print("Signature Verification PASSED!")
    else:
        print("Signature Verification FAILED!")

if __name__ == '__main__':
    test_sig()