from django.contrib import admin, messages
from django.conf import settings
from django.urls import path, reverse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from .models import Withdrawal, WithdrawalSettings, WithdrawalJayapay, WithdrawalService
from .integrations.jayapay import build_params, sign_params, send_cash_request
from .integrations.jayapay_banks import JAYAPAY_BANKS
from django.utils.html import format_html


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'bank_account', 'withdrawal_service', 'amount', 'fee', 'net_amount', 'status_display', 'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('user__phone', 'bank_account__account_number')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['process_withdrawal_jayapay']
    change_form_template = 'admin/withdrawal/change_form.html'
    autocomplete_fields = ('user', 'bank_account', 'transaction')
    list_select_related = ('user', 'bank_account', 'transaction', 'withdrawal_service')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'bank_account__bank', 'transaction')

    def status_display(self, obj):
        color_map = {
            'PENDING': '#f59e0b',      # amber
            'PROCESSING': '#3b82f6',   # blue
            'COMPLETED': '#10b981',    # green
            'REJECTED': '#ef4444',     # red
            'FAILED': '#ef4444',       # red
            'CANCELLED': '#9ca3af',    # gray
        }
        label = obj.status.title()
        color = color_map.get(obj.status, '#6b7280')  # default gray
        return format_html(
            '<span style="padding:2px 10px;border-radius:999px;background-color:{};color:#fff;font-weight:600;font-size:12px;">{}</span>',
            color,
            label,
        )
    status_display.short_description = 'Status'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:pk>/process-jayapay/',
                self.admin_site.admin_view(self.process_jayapay_view),
                name='withdrawal_withdrawal_process_jayapay',
            ),
        ]
        return custom + urls

    def process_jayapay_view(self, request, pk: int):
        try:
            wd = Withdrawal.objects.select_related('bank_account__bank', 'user').get(pk=pk)
        except Withdrawal.DoesNotExist:
            self.message_user(request, 'Withdrawal tidak ditemukan', level=messages.ERROR)
            return redirect(reverse('admin:withdrawal_withdrawal_changelist'))

        if not getattr(settings, 'JAYAPAY_ENABLED', False):
            self.message_user(request, 'Jayapay tidak aktif (JAYAPAY_ENABLED=false)', level=messages.ERROR)
            return redirect(reverse('admin:withdrawal_withdrawal_change', args=(wd.id,)))
        if not settings.JAYAPAY_MERCHANT_CODE or not settings.JAYAPAY_PRIVATE_KEY:
            self.message_user(request, 'Konfigurasi Jayapay belum lengkap', level=messages.ERROR)
            return redirect(reverse('admin:withdrawal_withdrawal_change', args=(wd.id,)))

        initial = {
            'bankCode': wd.bank_account.bank.code if wd.bank_account else '',
            'accountNumber': wd.bank_account.account_number if wd.bank_account else '',
            'accountName': wd.bank_account.account_name if wd.bank_account else '',
            'amount': str(wd.net_amount or wd.amount),
        }

        if request.method == 'POST':
            bank_code = request.POST.get('bankCode')
            account_number = request.POST.get('accountNumber')
            account_name = request.POST.get('accountName')
            amount = request.POST.get('amount')

            if not bank_code or not account_number or not account_name or not amount:
                self.message_user(request, 'Semua field harus diisi', level=messages.ERROR)
                context = dict(self.admin_site.each_context(request), withdrawal=wd, initial=initial)
                return TemplateResponse(request, 'admin/withdrawal_jayapay.html', context)

            # Override net_amount jika admin isi amount
            try:
                wd.net_amount = float(amount)
            except Exception:
                self.message_user(request, 'Amount tidak valid', level=messages.ERROR)
                context = dict(self.admin_site.each_context(request), withdrawal=wd, initial=initial)
                return TemplateResponse(request, 'admin/withdrawal_jayapay.html', context)

            try:
                params = build_params(
                    wd,
                    merchant_code=settings.JAYAPAY_MERCHANT_CODE,
                    bank_code=bank_code,
                    account_number=account_number,
                    account_name=account_name,
                    notify_url=settings.JAYAPAY_NOTIFY_URL,
                )
                params['sign'] = sign_params(params, settings.JAYAPAY_PRIVATE_KEY)
                resp = send_cash_request(params)
                # Persist traceability for admin action as well
                try:
                    jp_withdrawal, _ = WithdrawalJayapay.objects.get_or_create(
                        withdrawal=wd,
                        defaults={"request_params": params}
                    )
                    if jp_withdrawal and not jp_withdrawal.request_params:
                        jp_withdrawal.request_params = params
                        jp_withdrawal.response_payload = resp
                        jp_withdrawal.save(update_fields=['request_params', 'response_payload'])
                    else:
                        jp_withdrawal.response_payload = resp
                        jp_withdrawal.save(update_fields=['response_payload'])
                except Exception:
                    pass
                wd.status = 'PROCESSING'
                wd.save()
                self.message_user(request, f"Withdrawal #{wd.id} dikirim ke Jayapay", level=messages.SUCCESS)
                return redirect(reverse('admin:withdrawal_withdrawal_change', args=(wd.id,)))
            except Exception as e:
                self.message_user(request, f"Gagal kirim ke Jayapay: {e}", level=messages.ERROR)
                context = dict(self.admin_site.each_context(request), withdrawal=wd, initial=initial)
                return TemplateResponse(request, 'admin/withdrawal_jayapay.html', context)

        context = dict(self.admin_site.each_context(request), withdrawal=wd, initial=initial)
        return TemplateResponse(request, 'admin/withdrawal_jayapay.html', context)

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        if obj:
            initial = {
                'bankCode': obj.bank_account.bank.code if obj.bank_account else '',
                'accountNumber': obj.bank_account.account_number if obj.bank_account else '',
                'accountName': obj.bank_account.account_name if obj.bank_account else '',
                'amount': str(obj.net_amount or obj.amount),
            }
            context.update({
                'jayapay_initial': initial,
                'jayapay_banks': JAYAPAY_BANKS,
                'process_jayapay_url': reverse('admin:withdrawal_withdrawal_process_jayapay', args=(obj.id,)),
                'jayapay_enabled': getattr(settings, 'JAYAPAY_ENABLED', False),
            })
        return super().render_change_form(request, context, add, change, form_url, obj)

    def process_withdrawal_jayapay(self, request, queryset):
        if not getattr(settings, 'JAYAPAY_ENABLED', False):
            self.message_user(request, 'Jayapay tidak aktif (JAYAPAY_ENABLED=false)', level=messages.ERROR)
            return
        if not settings.JAYAPAY_MERCHANT_CODE or not settings.JAYAPAY_PRIVATE_KEY:
            self.message_user(request, 'Konfigurasi Jayapay belum lengkap', level=messages.ERROR)
            return

        processed = 0
        for wd in queryset.select_related('bank_account__bank'):
            if wd.status not in ('PENDING', 'PROCESSING'):
                self.message_user(request, f"Withdrawal #{wd.id} dilewati: status {wd.status}", level=messages.WARNING)
                continue
            if not wd.bank_account:
                self.message_user(request, f"Withdrawal #{wd.id} gagal: tidak ada bank_account", level=messages.ERROR)
                continue

            bank = wd.bank_account.bank
            try:
                params = build_params(
                    wd,
                    merchant_code=settings.JAYAPAY_MERCHANT_CODE,
                    bank_code=bank.code,
                    account_number=wd.bank_account.account_number,
                    account_name=wd.bank_account.account_name,
                    notify_url=settings.JAYAPAY_NOTIFY_URL,
                )
                params['sign'] = sign_params(params, settings.JAYAPAY_PRIVATE_KEY)
                resp = send_cash_request(params)
                # Persist traceability for bulk action
                try:
                    jp_withdrawal, _ = WithdrawalJayapay.objects.get_or_create(
                        withdrawal=wd,
                        defaults={"request_params": params}
                    )
                    if jp_withdrawal and not jp_withdrawal.request_params:
                        jp_withdrawal.request_params = params
                        jp_withdrawal.response_payload = resp
                        jp_withdrawal.save(update_fields=['request_params', 'response_payload'])
                    else:
                        jp_withdrawal.response_payload = resp
                        jp_withdrawal.save(update_fields=['response_payload'])
                except Exception:
                    pass
                wd.status = 'PROCESSING'
                wd.save()
                processed += 1
                self.message_user(request, f"Withdrawal #{wd.id} dikirim ke Jayapay", level=messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Withdrawal #{wd.id} gagal dikirim: {e}", level=messages.ERROR)

        if processed:
            self.message_user(request, f"Berhasil memproses {processed} withdrawal via Jayapay.", level=messages.SUCCESS)
    process_withdrawal_jayapay.short_description = 'Process via Jayapay'


@admin.register(WithdrawalJayapay)
class WithdrawalJayapayAdmin(WithdrawalAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(status__in=['PENDING', 'PROCESSING'])


@admin.register(WithdrawalSettings)
class WithdrawalSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'is_active', 'balance_source', 'require_bank_account', 'require_pin', 'require_active_investment', 'require_withdraw_service', 'minimum_product_quantity', 'required_product', 'updated_at'
    )
    list_filter = ('is_active',)
    search_fields = ('required_product__name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WithdrawalService)
class WithdrawalServiceAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'duration_hours',
        'fee_percent',
        'fee_fixed',
        'is_active',
        'sort_order',
        'updated_at',
    )
    list_filter = ('is_active',)
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
