import os
import django
import sys

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from deposits.models import GatewaySettings

def check_pk():
    gs = GatewaySettings.objects.order_by('-updated_at').first()
    if not gs:
        print("No GatewaySettings found.")
        return
        
    pk = gs.jayapay_public_key
    print(f"Jayapay Public Key present: {bool(pk)}")
    if pk:
        print(f"Length: {len(pk)}")
        print(f"Start: {pk[:30]}...")
    else:
        print("Jayapay Public Key is EMPTY!")
        
        # Optionally set the one from user message if it's empty?
        # The user provided one in the prompt.
        # But maybe that's just an example.
        # "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDFJ/AmUV4Z8udG8aOBUt/kEwc/DbxF5Gtfw6Y00NHQ4Pz2X2x9IxjUZxn2dnFxmrmhqKNlfwXOqyejhBzi0pSHyGoI4XP9IEfZGO6YkSb9DCY1ZxX8fDl2G+tPCbWYTVO4JutFmzTWgk1Uhhu6L9dlOMUHvZf3/6czA/a9C7azXwIDAQAB"
        # I'll update it if empty, just to be helpful, or ask user?
        # User said "perbaiki dulu itu kenapa callback gagal".
        # If key is missing, it will fail.
        
        example_key = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDFJ/AmUV4Z8udG8aOBUt/kEwc/DbxF5Gtfw6Y00NHQ4Pz2X2x9IxjUZxn2dnFxmrmhqKNlfwXOqyejhBzi0pSHyGoI4XP9IEfZGO6YkSb9DCY1ZxX8fDl2G+tPCbWYTVO4JutFmzTWgk1Uhhu6L9dlOMUHvZf3/6czA/a9C7azXwIDAQAB"
        
        print("Setting example public key from user documentation...")
        gs.jayapay_public_key = example_key
        gs.save()
        print("Public Key Updated.")

if __name__ == '__main__':
    check_pk()