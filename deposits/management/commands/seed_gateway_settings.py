from django.core.management.base import BaseCommand
from deposits.models import GatewaySettings


class Command(BaseCommand):
    help = 'Seed default gateway settings for Klikpay and Jayapay'

    def handle(self, *args, **options):
        # Provided seed values
        klikpay_public_key = ''
        klikpay_private_key = ''
        klikpay_merchant_code = ''
        klikpay_api_url = ''

        jayapay_public_key = ''
        jayapay_private_key = ''
        jayapay_merchant_code = ''
        jayapay_api_url = ''

        # Domain harus diisi manual di admin jika belum ada
        gs, created = GatewaySettings.objects.get_or_create(id=1)
        gs.default_wallet_type = 'BALANCE'
        gs.jayapay_enabled = True
        gs.klikpay_enabled = True
        gs.min_deposit_amount = gs.min_deposit_amount or 0
        gs.max_deposit_amount = gs.max_deposit_amount or 0

        # Klikpay
        gs.klikpay_public_key = klikpay_public_key
        gs.klikpay_private_key = klikpay_private_key
        gs.klikpay_merchant_code = klikpay_merchant_code
        gs.klikpay_api_url = klikpay_api_url
        # Gunakan endpoint callback statis agar konsisten dengan konfigurasi views
        gs.klikpay_callback_path = "api/deposits/klikpay/callback/"
        gs.klikpay_redirect_url = gs.klikpay_redirect_url or ''

        # Jayapay
        gs.jayapay_public_key = jayapay_public_key
        gs.jayapay_private_key = jayapay_private_key
        gs.jayapay_merchant_code = jayapay_merchant_code
        gs.jayapay_api_url = jayapay_api_url
        gs.jayapay_callback_path = "api/deposits/jayapay/callback/"
        gs.jayapay_redirect_url = gs.jayapay_redirect_url or ''

        gs.save()
        self.stdout.write(self.style.SUCCESS('Gateway settings seeded. Fill app_domain and redirect URLs in admin if needed.'))
