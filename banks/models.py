from django.conf import settings
from django.db import models
from django.utils import timezone


class BankSettings(models.Model):
    """Settings untuk konfigurasi bank system"""
    max_banks_per_user = models.PositiveSmallIntegerField(
        default=1,
        help_text="Maksimal jumlah bank yang bisa dimiliki user"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bank_settings'
        verbose_name = 'Bank Settings'
        verbose_name_plural = 'Bank Settings'

    def __str__(self):
        return f"Max Banks Per User: {self.max_banks_per_user}"

    @classmethod
    def get_max_banks_per_user(cls):
        """Get current max banks per user setting"""
        settings_obj = cls.objects.first()
        return settings_obj.max_banks_per_user if settings_obj else 1


class Bank(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    logo = models.URLField(blank=True, null=True)
    min_withdrawal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    max_withdrawal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    withdrawal_fee = models.DecimalField(max_digits=7, decimal_places=2, default=0)  # percentage or flat
    withdrawal_fee_fixed = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    processing_time = models.PositiveSmallIntegerField(default=1)  # in days

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'banks'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class UserBank(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_banks')
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name='user_banks')
    account_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_banks'
        constraints = [
            models.UniqueConstraint(fields=['user', 'bank'], name='unique_user_bank_combination'),
            models.UniqueConstraint(fields=['user'], condition=models.Q(is_default=True), name='unique_default_bank_per_user'),
        ]

    def __str__(self):
        return f"{self.user.phone} - {self.bank.name} {self.account_number}"

    def save(self, *args, **kwargs):
        # Jika ini adalah bank pertama user, set sebagai default
        if not UserBank.objects.filter(user=self.user).exists():
            self.is_default = True
        
        # Jika set sebagai default, unset default lainnya
        if self.is_default:
            UserBank.objects.filter(user=self.user, is_default=True).update(is_default=False)
        
        super().save(*args, **kwargs)
