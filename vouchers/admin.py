from django.contrib import admin
from .models import Voucher, VoucherUsage
from .forms import VoucherAdminForm


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    form = VoucherAdminForm
    list_display = (
        'code', 'type', 'claim_mode', 'amount', 'min_amount', 'max_amount', 'balance_type',
        'usage_limit', 'used_count', 'is_active', 'is_daily_claim', 'start_at', 'expires_at', 'created_at'
    )
    search_fields = ('code',)
    list_filter = ('is_active', 'is_daily_claim', 'balance_type', 'type', 'claim_mode')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('code', 'claim_mode', 'is_active', 'is_daily_claim', 'start_at', 'expires_at', 'balance_type', 'usage_limit')
        }),
        ('Reward Type', {
            'fields': ('type',)
        }),
        ('Fixed/Random Config', {
            'fields': ('amount', 'min_amount', 'max_amount'),
            'description': 'Isi untuk tipe fixed/random. Untuk random, gunakan min/max.'
        }),
        ('Rank Rewards (tanpa JSON)', {
            'fields': ('rank_1', 'rank_2', 'rank_3', 'rank_4', 'rank_5', 'rank_6'),
            'description': 'Masukkan nominal reward untuk rank 1–6. Tidak perlu input JSON.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(VoucherUsage)
class VoucherUsageAdmin(admin.ModelAdmin):
    list_display = (
        'voucher_code', 'user', 'amount_received', 'balance_type', 'used_at'
    )
    search_fields = ('voucher_code', 'user__phone')
    readonly_fields = ('used_at',)


# Register your models here.
