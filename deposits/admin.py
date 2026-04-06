from django.contrib import admin
from .models import GatewaySettings, Deposit


@admin.register(GatewaySettings)
class GatewaySettingsAdmin(admin.ModelAdmin):
    list_display = (
        'default_wallet_type', 'app_domain', 'min_deposit_amount', 'max_deposit_amount', 'jayapay_enabled', 'klikpay_enabled', 'updated_at'
    )
    readonly_fields = ('updated_at',)
    fieldsets = (
        ('Global', {
            'fields': ('default_wallet_type', 'app_domain', 'min_deposit_amount', 'max_deposit_amount', 'jayapay_enabled', 'klikpay_enabled')
        }),
        ('Jayapay', {
            'fields': (
                'jayapay_merchant_code',
                'jayapay_private_key',
                'jayapay_public_key',
                'jayapay_api_url',
                'jayapay_callback_path',
                'jayapay_redirect_url',
            ),
            'description': 'Konfigurasi Jayapay (merchant code, keys, API URL, callback path, redirect URL).'
        }),
        ('Klikpay', {
            'fields': (
                'klikpay_api_url',
                'klikpay_merchant_code',
                'klikpay_secret_key',
                'klikpay_private_key',
                'klikpay_public_key',
                'klikpay_callback_path',
                'klikpay_redirect_url',
            ),
            'description': 'Konfigurasi Klikpay (API URL, merchant code, keys, callback path, redirect URL).'
        }),
    )


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('order_num', 'user', 'gateway', 'amount', 'wallet_type', 'status', 'created_at')
    list_filter = ('gateway', 'status', 'wallet_type')
    search_fields = ('order_num', 'user__phone', 'user__username')
    readonly_fields = ('created_at', 'updated_at', 'payment_url', 'request_params', 'response_payload', 'callback_payload', 'callback_at')
