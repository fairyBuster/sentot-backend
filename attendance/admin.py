from django.contrib import admin
from .models import AttendanceSettings, AttendanceLog
from .forms import AttendanceSettingsAdminForm


@admin.register(AttendanceSettings)
class AttendanceSettingsAdmin(admin.ModelAdmin):
    form = AttendanceSettingsAdminForm
    list_display = (
        'id', 'balance_source', 'reward_type', 'fixed_amount', 'min_amount', 'max_amount',
        'consecutive_bonus_enabled', 'bonus_claim_separate_enabled', 'bonus_7_days', 'bonus_30_days', 'is_active', 'created_at'
    )

    def has_add_permission(self, request):
        # Cukup satu konfigurasi, kalau sudah ada maka tidak bisa tambah baru
        return not AttendanceSettings.objects.exists()
    list_filter = ('is_active', 'balance_source', 'reward_type', 'consecutive_bonus_enabled', 'bonus_claim_separate_enabled')
    search_fields = ('id',)
    readonly_fields = ('created_at', 'updated_at')

    def get_fieldsets(self, request, obj=None):
        cycle_days_raw = None
        if request.method == 'POST':
            cycle_days_raw = (request.POST.get('daily_cycle_days') or '').strip()
        elif request.method == 'GET':
            cycle_days_raw = (request.GET.get('daily_cycle_days') or '').strip()

        cycle_days = None
        if cycle_days_raw:
            try:
                cycle_days = int(cycle_days_raw)
            except Exception:
                cycle_days = None
        if cycle_days is None:
            cycle_days = int(getattr(obj, 'daily_cycle_days', 7) or 7)
        if cycle_days <= 0:
            cycle_days = 7
        if cycle_days > 31:
            cycle_days = 31

        reward_type = None
        if request.method == 'POST':
            reward_type = (request.POST.get('reward_type') or '').strip() or None
        if reward_type is None:
            reward_type = getattr(obj, 'reward_type', None)

        daily_fields = ('daily_cycle_days',) + tuple(f'day_{i}' for i in range(1, cycle_days + 1))

        if reward_type == 'daily':
            bonus_fields = ('consecutive_bonus_enabled', 'bonus_claim_separate_enabled', 'bonus_7_days')
            bonus_desc = f'Jika ON: bonus diberikan di hari terakhir siklus (Day {cycle_days}).'
        else:
            bonus_fields = ('consecutive_bonus_enabled', 'bonus_claim_separate_enabled', 'bonus_7_days', 'bonus_30_days')
            bonus_desc = None

        fieldsets = (
            (None, {
                'fields': ('balance_source', 'reward_type', 'is_active')
            }),
            ('Base Reward', {
                'fields': ('fixed_amount', 'min_amount', 'max_amount')
            }),
            ('Rank Rewards (tanpa JSON)', {
                'fields': ('rank_1', 'rank_2', 'rank_3', 'rank_4', 'rank_5', 'rank_6'),
                'description': 'Isi nominal untuk rank 1–6. Tidak perlu JSON.'
            }),
            ('Daily Rewards (Cycle)', {
                'fields': daily_fields,
                'description': f'Isi nominal untuk setiap hari dalam siklus (1–{cycle_days}). Setelah hari {cycle_days}, akan kembali ke hari 1.'
            }),
            ('Bonus Beruntun', {
                'fields': bonus_fields,
                **({'description': bonus_desc} if bonus_desc else {})
            }),
            ('Timestamps', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            }),
        )
        return fieldsets


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ('user_phone', 'date', 'streak_count', 'amount', 'created_at')
    search_fields = ('user__phone',)
    list_filter = ('date',)
    readonly_fields = ('created_at',)

    def user_phone(self, obj):
        return obj.user.phone
    user_phone.short_description = 'Phone'
