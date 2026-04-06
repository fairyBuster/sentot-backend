from django.db import models
from django.conf import settings
from products.models import Transaction


class GatewaySettings(models.Model):
    WALLET_CHOICES = [
        ('BALANCE', 'Balance'),
        ('BALANCE_DEPOSIT', 'Balance Deposit'),
    ]

    # Global controls
    default_wallet_type = models.CharField(max_length=20, choices=WALLET_CHOICES, default='BALANCE')
    app_domain = models.CharField(max_length=255, blank=True, default='', help_text='Contoh: myapp.example.com (tanpa http/https)')
    min_deposit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Minimal nominal deposit (0 = tidak dibatasi)')
    max_deposit_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text='Maksimal nominal deposit (0 = tidak dibatasi)')
    jayapay_enabled = models.BooleanField(default=True)
    klikpay_enabled = models.BooleanField(default=False)

    # Jayapay config
    jayapay_merchant_code = models.CharField(max_length=100, blank=True, default='')
    jayapay_private_key = models.TextField(blank=True, default='', help_text='Paste RSA PRIVATE KEY body ONLY (without BEGIN/END headers)')
    jayapay_public_key = models.TextField(blank=True, default='', help_text='Optional: PUBLIC KEY untuk verifikasi/dekripsi callback bila diperlukan')
    jayapay_api_url = models.CharField(max_length=255, blank=True, default='')
    jayapay_callback_path = models.CharField(max_length=255, blank=True, default='', help_text='Contoh: gateway/payment/notify_xxx')
    jayapay_redirect_url = models.CharField(max_length=255, blank=True, default='')

    # Klikpay config
    klikpay_api_url = models.CharField(max_length=255, blank=True, default='')
    klikpay_merchant_code = models.CharField(max_length=100, blank=True, default='')
    klikpay_secret_key = models.CharField(max_length=255, blank=True, default='')
    klikpay_private_key = models.TextField(blank=True, default='', help_text='Optional: PRIVATE KEY jika penyedia memerlukan RSA signing')
    klikpay_public_key = models.TextField(blank=True, default='', help_text='Optional: PUBLIC KEY jika penyedia memerlukan')
    klikpay_callback_path = models.CharField(max_length=255, blank=True, default='', help_text='Contoh: gateway/payment/notify_xxx')
    klikpay_redirect_url = models.CharField(max_length=255, blank=True, default='')

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Gateway Settings (default={self.default_wallet_type})"

    class Meta:
        verbose_name = 'Gateway Settings'
        verbose_name_plural = 'Gateway Settings'


class Deposit(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    GATEWAY_CHOICES = [
        ('JAYAPAY', 'Jayapay'),
        ('KLIKPAY', 'Klikpay'),
    ]
    WALLET_CHOICES = [
        ('BALANCE', 'Balance'),
        ('BALANCE_DEPOSIT', 'Balance Deposit'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES)
    order_num = models.CharField(max_length=60, unique=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    wallet_type = models.CharField(max_length=20, choices=WALLET_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True)
    payment_url = models.CharField(max_length=500, blank=True, default='')

    request_params = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    callback_payload = models.JSONField(null=True, blank=True)
    callback_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order_num} - {self.gateway} - {self.user_id}"

    class Meta:
        db_table = 'deposits'
        ordering = ['-created_at']
