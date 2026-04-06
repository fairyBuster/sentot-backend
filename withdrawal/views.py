from rest_framework import generics, permissions, status
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .models import Withdrawal, WithdrawalSettings, WithdrawalService
from .serializers import WithdrawalSerializer, WithdrawalSettingsSerializer, WithdrawalServiceSerializer
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import logging
from rest_framework.views import APIView
from django.http import HttpResponse

from .integrations.jayapay import build_params, sign_params_legacy, send_cash_request
from .models import JayapayWithdrawal
from products.models import Transaction
from products.serializers import TransactionSerializer
from django.db.models import Q
from zoneinfo import ZoneInfo
from datetime import datetime, time, timedelta

logger = logging.getLogger(__name__)

class WithdrawalSettingsView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = WithdrawalSettingsSerializer

    @extend_schema(summary='Get withdrawal settings')
    def get_object(self):
        return WithdrawalSettings.objects.order_by('-updated_at').first()


class WithdrawalServiceListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = WithdrawalServiceSerializer
    throttle_scope = 'withdrawals'

    @extend_schema(summary='List withdrawal services (active)')
    def get_queryset(self):
        return WithdrawalService.objects.filter(is_active=True).order_by('sort_order', 'duration_hours', 'name')


class WithdrawalListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WithdrawalSerializer
    throttle_scope = 'withdrawals'

    def get_queryset(self):
        return Withdrawal.objects.filter(user=self.request.user).order_by('-created_at')

    @extend_schema(summary='List user withdrawals')
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary='Request withdrawal',
        parameters=[
            OpenApiParameter(name='bank_account_id', description='UserBank ID (optional, default account used if omitted)', required=False, type=int),
        ],
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'amount': {'type': 'string', 'description': 'Withdrawal amount'},
                    'bank_account_id': {'type': 'integer', 'nullable': True},
                    'pin': {'type': 'string', 'description': '6-digit PIN if required', 'nullable': True},
                    'service_id': {'type': 'integer', 'description': 'ID jasa withdraw', 'nullable': True},
                },
                'required': ['amount']
            }
        }
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class JayapayInitiateView(APIView):
    permission_classes = [permissions.IsAdminUser]
    throttle_scope = 'withdraw_admin_initiate'

    @extend_schema(
        summary="Inisiasi withdraw otomatis via Jayapay (admin)",
        parameters=[
            OpenApiParameter(name="pk", description="Withdrawal ID", required=True, type=int),
        ],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "bankCode": {"type": "string"},
                    "accountNumber": {"type": "string"},
                    "accountName": {"type": "string"},
                },
                "required": ["bankCode", "accountNumber", "accountName"],
            }
        },
    )
    def post(self, request, pk: int):
        gs = WithdrawalSettings.objects.first()
        jayapay_enabled = bool(gs and gs.jayapay_enabled)
        merchant_code = (gs.jayapay_merchant_code or '').strip() if gs else ''
        private_key = (gs.jayapay_private_key or '').strip() if gs else ''
        app_domain = (gs.app_domain or '').strip() if gs else ''

        if not jayapay_enabled:
            return Response({"detail": "Jayapay tidak aktif"}, status=status.HTTP_400_BAD_REQUEST)
        if not merchant_code or not private_key:
            return Response({"detail": "Konfigurasi Jayapay belum lengkap"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            withdrawal = Withdrawal.objects.select_related("user").get(pk=pk)
        except Withdrawal.DoesNotExist:
            return Response({"detail": "Withdrawal tidak ditemukan"}, status=status.HTTP_404_NOT_FOUND)

        if withdrawal.status not in ["PENDING", "PROCESSING"]:
            return Response({"detail": "Status withdrawal tidak valid untuk inisiasi"}, status=status.HTTP_400_BAD_REQUEST)

        bank_code = request.data.get("bankCode")
        account_number = request.data.get("accountNumber")
        account_name = request.data.get("accountName")
        if not bank_code or not account_number or not account_name:
            return Response({"detail": "bankCode, accountNumber, accountName wajib diisi"}, status=status.HTTP_400_BAD_REQUEST)

        notify_url = f"https://{app_domain}/api/withdrawals/jayapay/callback/"
        params = build_params(
            withdrawal,
            merchant_code=merchant_code,
            bank_code=bank_code,
            account_number=account_number,
            account_name=account_name,
            notify_url=notify_url,
        )

        try:
            params["sign"] = sign_params_legacy(params, private_key)
        except Exception as e:
            logger.error(f"Jayapay signature creation failed for withdrawal {pk}: {e}", exc_info=True)
            return Response({"detail": f"Gagal membuat tanda tangan: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure JayapayWithdrawal record exists for traceability
        jp_withdrawal, _ = JayapayWithdrawal.objects.get_or_create(
            withdrawal=withdrawal,
            defaults={"request_params": params}
        )
        if jp_withdrawal and not jp_withdrawal.request_params:
            jp_withdrawal.request_params = params
            jp_withdrawal.save(update_fields=["request_params"])

        try:
            logger.info(f"Sending Jayapay request for withdrawal {pk} with params: {{k: v for k, v in params.items() if k != 'sign'}}")
            resp = send_cash_request(params)
            logger.info(f"Jayapay response for withdrawal {pk}: {resp}")
        except Exception as e:
            withdrawal.status = "PROCESSING"
            withdrawal.save()
            jp_withdrawal.response_payload = {'error': str(e)}
            jp_withdrawal.save(update_fields=['response_payload'])
            logger.error(f"Jayapay request failed for withdrawal {pk}: {e}", exc_info=True)
            return Response({"detail": f"Gagal kirim ke Jayapay: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        jp_withdrawal.response_payload = resp
        jp_withdrawal.save(update_fields=['response_payload'])

        withdrawal.status = "PROCESSING"
        withdrawal.save()
        return Response({"jayapay": resp, "submitted_params": {k: v for k, v in params.items() if k != "sign"}}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class JayapayCallbackView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'gateway_callback'

    @extend_schema(summary="Callback Jayapay untuk update status withdraw")
    def post(self, request, *args, **kwargs):
        data = request.data if isinstance(request.data, dict) else {}
        # Logging payload masuk untuk diagnosa callback
        try:
            logger.info(f"Jayapay callback received: {data}")
        except Exception:
            logger.warning("Jayapay callback: failed to log payload")
        order_num = data.get("orderNum") or data.get("order_no") or ""
        status_str = str(data.get("status") or data.get("order_status") or "").lower()
        status_msg = str(data.get("statusMsg") or data.get("status_msg") or "").lower()

        # Support unified code WD-... and legacy W<withdrawal.id>...
        wid = None
        if order_num.startswith("WD-"):
            # Find withdrawal via linked transaction.trx_id
            try:
                from products.models import Transaction
                trx = Transaction.objects.filter(trx_id=order_num).first()
                if trx:
                    linked = Withdrawal.objects.filter(transaction=trx).first()
                    if linked:
                        wid = linked.pk
                        withdrawal = linked
                    else:
                        withdrawal = None
                else:
                    withdrawal = None
            except Exception:
                withdrawal = None
        elif order_num.startswith("W"):
            # Legacy path: extract numeric digits after 'W' as withdrawal.id
            wid_digits = []
            for ch in order_num[1:]:
                if ch.isdigit():
                    wid_digits.append(ch)
                else:
                    break
            if wid_digits:
                try:
                    wid = int("".join(wid_digits))
                    withdrawal = Withdrawal.objects.get(pk=wid)
                except Exception:
                    withdrawal = None
            else:
                withdrawal = None
        else:
            return Response({"detail": "orderNum tidak valid"}, status=status.HTTP_400_BAD_REQUEST)

        if not withdrawal:
            logger.warning(f"Jayapay callback: withdrawal not found for order {order_num}")
            return Response("SUCCESS")

        mapped = None
        # Jayapay status normalization per spec:
        # 0: Pending processing -> PROCESSING
        # 1: Processing -> PROCESSING
        # 2: Payment successful -> COMPLETED
        # 4: Payment failed -> REJECTED
        # 5: Bank payment in progress -> PROCESSING
        if status_str in {"success", "sukses", "completed", "finish", "done", "2"}:
            mapped = "COMPLETED"
        elif status_str in {"failed", "gagal", "reject", "rejected", "4"}:
            mapped = "REJECTED"
        elif status_str in {"processing", "pending", "0", "1", "5"} or status_msg in {"apply", "applied", "processing", "pending"}:
            mapped = "PROCESSING"

        if not mapped:
            logger.warning(f"Jayapay callback: unrecognized status for order {order_num}: status={status_str} statusMsg={status_msg}")
            return HttpResponse("SUCCESS", content_type="text/plain")

        withdrawal.status = mapped
        withdrawal.save()
        # Per JayaPay spec, always respond plain text "SUCCESS" to stop retries
        return HttpResponse("SUCCESS", content_type="text/plain")


class WithdrawalTransactionsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'transactions'

    @extend_schema(
        summary="Daftar transaksi Withdraw",
        parameters=[
            OpenApiParameter(name='status', type=str, description='Filter status transaksi'),
            OpenApiParameter(name='wallet_type', type=str, description='Filter wallet (BALANCE/BALANCE_DEPOSIT)'),
            OpenApiParameter(name='start_date', type=str, description='Tanggal mulai (YYYY-MM-DD)'),
            OpenApiParameter(name='end_date', type=str, description='Tanggal akhir (YYYY-MM-DD)'),
            OpenApiParameter(name='order_num', type=str, description='Filter berdasarkan nomor order (trx_id)'),
            OpenApiParameter(name='bank_account_id', type=int, description='Filter berdasarkan ID rekening pengguna'),
        ],
        responses=TransactionSerializer(many=True),
        description='Mengambil daftar transaksi bertipe WITHDRAW untuk user saat ini atau semua jika admin.'
    )
    def get(self, request):
        # Base queryset: admin melihat semua; user melihat miliknya atau referral
        if request.user.is_staff:
            queryset = Transaction.objects.all()
        else:
            queryset = Transaction.objects.filter(Q(user=request.user) | Q(upline_user=request.user))

        queryset = queryset.select_related('user', 'product', 'upline_user').prefetch_related(
            'related_withdrawal',
            'related_withdrawal__bank_account',
            'related_withdrawal__bank_account__bank',
            'related_withdrawal__withdrawal_service',
        )

        # Hanya transaksi bertipe WITHDRAW
        queryset = queryset.filter(type='WITHDRAW')

        # Query params
        status_param = request.query_params.get('status')
        wallet_type = request.query_params.get('wallet_type')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        order_num = request.query_params.get('order_num')
        bank_account_id = request.query_params.get('bank_account_id')

        # Filter langsung di Transaction
        if status_param:
            queryset = queryset.filter(status=status_param)
        if wallet_type:
            queryset = queryset.filter(wallet_type=wallet_type)
        tz = ZoneInfo('Asia/Jakarta')
        if start_date:
            try:
                sd = datetime.strptime(start_date, '%Y-%m-%d').date()
                start_dt = datetime.combine(sd, time.min, tz)
                queryset = queryset.filter(created_at__gte=start_dt)
            except ValueError:
                pass
        if end_date:
            try:
                ed = datetime.strptime(end_date, '%Y-%m-%d').date()
                end_exclusive = datetime.combine(ed + timedelta(days=1), time.min, tz)
                queryset = queryset.filter(created_at__lt=end_exclusive)
            except ValueError:
                pass
        if order_num:
            queryset = queryset.filter(trx_id=order_num)

        # Filter melalui relasi Withdrawal (bank_account_id, atau jika order_num dipakai via relasi)
        if bank_account_id:
            wd_qs = Withdrawal.objects.all() if request.user.is_staff else Withdrawal.objects.filter(user=request.user)
            wd_qs = wd_qs.filter(bank_account_id=bank_account_id)
            queryset = queryset.filter(id__in=wd_qs.values_list('transaction_id', flat=True))

        serializer = TransactionSerializer(queryset, many=True)
        return Response(serializer.data)
