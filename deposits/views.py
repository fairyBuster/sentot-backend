from django.conf import settings
from django.utils import timezone
from django.db import transaction as db_transaction
from django.shortcuts import redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, OpenApiExample
from decimal import Decimal, InvalidOperation
import uuid
import requests

from products.models import Transaction
from products.serializers import TransactionSerializer
from .models import GatewaySettings, Deposit
from withdrawal.integrations.jayapay import sign_params_legacy
from .integrations.klikpay import build_params as klikpay_build_params, sign_params as klikpay_sign_params, send_prepaid_request as klikpay_send_prepaid
from .utils import verify_jayapay_signature
from django.db.models import Q
from zoneinfo import ZoneInfo
from datetime import datetime, time, timedelta


def format_datetime(dt):
    return dt.strftime('%Y%m%d%H%M%S')


class JayapayDepositInitiateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'deposit_initiate'

    @extend_schema(
        summary="Inisiasi deposit via Jayapay",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "example": 100000},
                    "wallet_type": {"type": "string", "enum": ["BALANCE", "BALANCE_DEPOSIT"], "example": "BALANCE"},
                },
                "required": ["amount"],
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "order_num": {"type": "string", "example": "DEP-20250101XXXX-ABC123"},
                    "payment_url": {"type": "string", "example": "https://gateway.example/pay?id=..."},
                },
            },
            400: {"description": "Permintaan tidak valid"},
            502: {"description": "Gagal menghubungi gateway"},
        },
    )
    def post(self, request):
        gs = GatewaySettings.objects.order_by('-updated_at').first()
        # Gunakan konfigurasi dari admin saja (tanpa fallback .env)
        jayapay_enabled = bool(gs and gs.jayapay_enabled)
        merchant_code = (gs.jayapay_merchant_code or '').strip() if gs else ''
        private_key = (gs.jayapay_private_key or '').strip() if gs else ''
        app_domain = (gs.app_domain or '').strip() if gs else ''
        min_deposit_amount = (gs.min_deposit_amount or Decimal('0')) if gs else Decimal('0')
        max_deposit_amount = (gs.max_deposit_amount or Decimal('0')) if gs else Decimal('0')

        if not jayapay_enabled:
            return Response({'detail': 'Jayapay tidak aktif'}, status=status.HTTP_400_BAD_REQUEST)
        if not merchant_code or not private_key:
            return Response({'detail': 'Konfigurasi Jayapay belum lengkap'}, status=status.HTTP_400_BAD_REQUEST)
        if not app_domain:
            return Response({'detail': 'Konfigurasi domain untuk callback belum diisi'}, status=status.HTTP_400_BAD_REQUEST)

        wallet_type = (gs.default_wallet_type if gs and gs.default_wallet_type else 'BALANCE')
        if wallet_type not in ('BALANCE', 'BALANCE_DEPOSIT'):
            return Response({'detail': 'wallet_type tidak valid'}, status=status.HTTP_400_BAD_REQUEST)

        amount_raw = request.data.get('amount')
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise InvalidOperation()
        except Exception:
            return Response({'detail': 'amount tidak valid'}, status=status.HTTP_400_BAD_REQUEST)
        
        if min_deposit_amount and min_deposit_amount > 0 and amount < min_deposit_amount:
            return Response({'detail': f'Minimal deposit adalah {min_deposit_amount}'}, status=status.HTTP_400_BAD_REQUEST)
        if max_deposit_amount and max_deposit_amount > 0 and amount > max_deposit_amount:
            return Response({'detail': f'Maksimal deposit adalah {max_deposit_amount}'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        order_num = f"DEP-{timezone.localtime(timezone.now(), ZoneInfo('Asia/Jakarta')).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # Buat Transaction PENDING untuk deposit ini
        trx = Transaction.objects.create(
            user=user,
            product=None,
            type='DEPOSIT',
            amount=amount,
            description=f'Deposit via Jayapay ({wallet_type})',
            status='PENDING',
            wallet_type=wallet_type,
            trx_id=order_num,
        )

        # Jayapay membutuhkan jumlah integer string
        pay_money = str(int(round(float(amount))))
        now = timezone.localtime(timezone.now(), ZoneInfo('Asia/Jakarta'))
        # Notify URL: gunakan endpoint statis agar konsisten
        notify_url = f"https://{app_domain}/api/deposits/jayapay/callback/"

        # Payload lengkap untuk prepaid order
        params = {
            'merchantCode': merchant_code,
            'orderType': '0',
            'method': '',
            'orderNum': order_num,
            'payMoney': pay_money,
            'name': user.full_name or user.username,
            'email': getattr(user, 'email', '') or '',
            'phone': getattr(user, 'phone', '') or '',
            'notifyUrl': notify_url,
            'dateTime': format_datetime(now),
            'expiryPeriod': '1000',
            'productDetail': 'Top Up Saldo',
        }

        try:
            # Tanda tangan gaya lama: private-encrypt berchunk atas seluruh nilai terurut
            sign = sign_params_legacy(params, private_key)
        except Exception as e:
            trx.status = 'FAILED'
            trx.save(update_fields=['status'])
            return Response({'detail': f'Gagal membuat signature: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        params['sign'] = sign

        # Catat Deposit sebelum request
        dep = Deposit.objects.create(
            user=user,
            gateway='JAYAPAY',
            order_num=order_num,
            amount=amount,
            wallet_type=wallet_type,
            status='PENDING',
            transaction=trx,
            request_params=params,
        )

        # Kirim ke Jayapay prepaidOrder
        try:
            jayapay_url = (gs.jayapay_api_url or '').strip() if gs else ''
            api_url = jayapay_url or 'https://openapi.jayapayment.com/gateway/prepaidOrder'
            resp = requests.post(api_url, json=params, timeout=30)
            data = resp.json()
        except Exception as e:
            trx.status = 'FAILED'
            trx.save(update_fields=['status'])
            dep.response_payload = {'error': str(e)}
            dep.status = 'FAILED'
            dep.save(update_fields=['response_payload', 'status'])
            return Response({'detail': f'Gagal menghubungi gateway: {str(e)}'}, status=status.HTTP_502_BAD_GATEWAY)

        if data.get('platRespCode') == 'SUCCESS':
            payment_url = data.get('url')
            if payment_url:
                dep.payment_url = payment_url
                dep.response_payload = data
                dep.save(update_fields=['payment_url', 'response_payload'])
                return Response({'order_num': order_num, 'payment_url': payment_url}, status=status.HTTP_200_OK)
            else:
                trx.status = 'FAILED'
                trx.save(update_fields=['status'])
                dep.response_payload = data
                dep.status = 'FAILED'
                dep.save(update_fields=['response_payload', 'status'])
                return Response({'detail': 'Gateway tidak mengembalikan URL pembayaran'}, status=status.HTTP_502_BAD_GATEWAY)
        else:
            trx.status = 'FAILED'
            trx.save(update_fields=['status'])
            dep.response_payload = data
            dep.status = 'FAILED'
            dep.save(update_fields=['response_payload', 'status'])
            return Response({'detail': data.get('platRespMessage') or 'Pembayaran gagal'}, status=status.HTTP_400_BAD_REQUEST)


class JayapayDepositCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'gateway_callback'

    def post(self, request):
        gs = GatewaySettings.objects.order_by('-updated_at').first()
        callback = request.data
        code = callback.get('code')
        msg = callback.get('msg')
        order_num = callback.get('orderNum')

        # Jayapay selalu expect 'SUCCESS' di response
        if not order_num:
            return Response('SUCCESS')

        try:
            trx = Transaction.objects.get(trx_id=order_num)
        except Transaction.DoesNotExist:
            # Unknown order, acknowledge to avoid retry storms
            return Response('SUCCESS')

        # Update Deposit callback payload
        try:
            dep = Deposit.objects.get(order_num=order_num)
            dep.callback_payload = callback
            dep.callback_at = timezone.now()
            dep.save(update_fields=['callback_payload', 'callback_at'])
        except Deposit.DoesNotExist:
            pass

        # Jika sudah selesai, abaikan
        if trx.status == 'COMPLETED':
            return Response('SUCCESS')

        if code == '00' and msg == 'SUCCESS':
            # Verify callback signature using Public Key
            is_valid = False
            try:
                public_key = (gs.jayapay_public_key or '').strip() if gs else ''
                
                if public_key:
                    is_valid = verify_jayapay_signature(callback, public_key)
                else:
                    # If public key missing, we cannot verify. Fail safe.
                    # Or check if private key exists (maybe user put it there?)
                    # But per docs, we need PLATFORM PUBLIC KEY.
                    is_valid = False
            except Exception:
                is_valid = False
            
            if not is_valid:
                # Log spoof attempt or configuration error
                if trx.status in ('PENDING', 'PROCESSING'):
                    trx.status = 'FAILED'
                    trx.description += " [Invalid Callback Signature]"
                    trx.save(update_fields=['status', 'description'])
                    try:
                        dep = Deposit.objects.get(order_num=order_num)
                        dep.status = 'FAILED'
                        dep.save(update_fields=['status'])
                    except Deposit.DoesNotExist:
                        pass
                return Response('SUCCESS')

            user = trx.user
            wallet_field = 'balance' if trx.wallet_type == 'BALANCE' else 'balance_deposit'
            with db_transaction.atomic():
                current_balance = getattr(user, wallet_field)
                setattr(user, wallet_field, current_balance + trx.amount)
                user.save(update_fields=[wallet_field])
                trx.status = 'COMPLETED'
                trx.save(update_fields=['status'])
                # Mark deposit completed
                try:
                    dep = Deposit.objects.get(order_num=order_num)
                    dep.status = 'COMPLETED'
                    dep.save(update_fields=['status'])
                except Deposit.DoesNotExist:
                    pass
            return Response('SUCCESS')
        else:
            # Mark as failed only if previously pending/processing
            if trx.status in ('PENDING', 'PROCESSING'):
                trx.status = 'FAILED'
                trx.save(update_fields=['status'])
                try:
                    dep = Deposit.objects.get(order_num=order_num)
                    dep.status = 'FAILED'
                    dep.save(update_fields=['status'])
                except Deposit.DoesNotExist:
                    pass
            return Response('SUCCESS')


class KlikpayDepositInitiateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'deposit_initiate'

    @extend_schema(
        summary="Inisiasi deposit via Klikpay",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "example": 50000},
                    "wallet_type": {"type": "string", "enum": ["BALANCE", "BALANCE_DEPOSIT"], "example": "BALANCE"},
                },
                "required": ["amount"],
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "order_num": {"type": "string", "example": "DEP-20250101XXXX-XYZ789"},
                    "payment_url": {"type": "string", "example": "https://klikpay.example/pay?id=..."},
                },
            },
            400: {"description": "Permintaan tidak valid"},
            502: {"description": "Gagal menghubungi gateway"},
        },
    )
    def post(self, request):
        gs = GatewaySettings.objects.order_by('-updated_at').first()
        klikpay_enabled = bool(gs and gs.klikpay_enabled)
        api_url = (gs.klikpay_api_url or '').strip() if gs else ''
        merchant_code = (gs.klikpay_merchant_code or '').strip() if gs else ''
        private_key = (gs.klikpay_private_key or '').strip() if gs else ''
        redirect_url = (gs.klikpay_redirect_url or '').strip() if gs else ''
        app_domain = (gs.app_domain or '').strip() if gs else ''
        min_deposit_amount = (gs.min_deposit_amount or Decimal('0')) if gs else Decimal('0')
        max_deposit_amount = (gs.max_deposit_amount or Decimal('0')) if gs else Decimal('0')

        if not klikpay_enabled:
            return Response({'detail': 'Klikpay tidak aktif'}, status=status.HTTP_400_BAD_REQUEST)
        if not api_url or not merchant_code or not private_key:
            return Response({'detail': 'Konfigurasi Klikpay belum lengkap'}, status=status.HTTP_400_BAD_REQUEST)
        if not app_domain:
            return Response({'detail': 'Konfigurasi domain untuk callback belum diisi'}, status=status.HTTP_400_BAD_REQUEST)
        
        wallet_type = 'BALANCE_DEPOSIT'

        amount_raw = request.data.get('amount')
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise InvalidOperation()
        except Exception:
            return Response({'detail': 'amount tidak valid'}, status=status.HTTP_400_BAD_REQUEST)
        
        if min_deposit_amount and min_deposit_amount > 0 and amount < min_deposit_amount:
            return Response({'detail': f'Minimal deposit adalah {min_deposit_amount}'}, status=status.HTTP_400_BAD_REQUEST)
        if max_deposit_amount and max_deposit_amount > 0 and amount > max_deposit_amount:
            return Response({'detail': f'Maksimal deposit adalah {max_deposit_amount}'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        order_num = f"DEP-{timezone.localtime(timezone.now(), ZoneInfo('Asia/Jakarta')).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        trx = Transaction.objects.create(
            user=user,
            product=None,
            type='DEPOSIT',
            amount=amount,
            description=f'Deposit via Klikpay ({wallet_type})',
            status='PENDING',
            wallet_type=wallet_type,
            trx_id=order_num,
        )

        amount_int = str(int(round(float(amount))))
        notify_url = f"https://{app_domain}/api/deposits/klikpay/callback/"
        params = klikpay_build_params(
            order_num=order_num,
            amount_int=amount_int,
            user_name=user.full_name or user.username,
            user_email=getattr(user, 'email', '') or '',
            user_phone=getattr(user, 'phone', '') or '',
            notify_url=notify_url,
            redirect_url=redirect_url,
            expiry_period='1440',
            product_detail='Top Up Saldo',
        )
        params["merchantCode"] = merchant_code
        params["sign"] = klikpay_sign_params(params, private_key)

        dep = Deposit.objects.create(
            user=user,
            gateway='KLIKPAY',
            order_num=order_num,
            amount=amount,
            wallet_type=wallet_type,
            status='PENDING',
            transaction=trx,
            request_params=params,
        )
        try:
            api_url = api_url or 'https://idvs.klysnv.com/gateway/prepaidOrder'
            data = klikpay_send_prepaid(api_url, params)
        except Exception as e:
            trx.status = 'FAILED'
            trx.save(update_fields=['status'])
            dep.response_payload = {'error': str(e)}
            dep.status = 'FAILED'
            dep.save(update_fields=['response_payload', 'status'])
            return Response({'detail': f'Gagal menghubungi gateway: {str(e)}'}, status=status.HTTP_502_BAD_GATEWAY)

        # Placeholder success detection; adjust per Klikpay response format
        payment_url = data.get('payment_url') or data.get('url')
        resp_code = str(data.get('code') or data.get('status') or '').upper()
        is_success = resp_code in ('SUCCESS', '00', '200') or bool(payment_url)
        if is_success and payment_url:
            dep.payment_url = payment_url
            dep.response_payload = data
            dep.save(update_fields=['payment_url', 'response_payload'])
            return Response({'order_num': order_num, 'payment_url': payment_url}, status=status.HTTP_200_OK)
        else:
            trx.status = 'FAILED'
            trx.save(update_fields=['status'])
            dep.response_payload = data
            dep.status = 'FAILED'
            dep.save(update_fields=['response_payload', 'status'])
            return Response({'detail': data.get('message') or 'Pembayaran gagal'}, status=status.HTTP_400_BAD_REQUEST)


class KlikpayDepositCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'gateway_callback'

    def post(self, request):
        gs = GatewaySettings.objects.first()
        callback = request.data
        order_num = callback.get('orderNum') or callback.get('order_id') or callback.get('orderId')
        status_val = str(callback.get('status') or '').upper()
        code = str(callback.get('code') or '').upper()
        msg = str(callback.get('msg') or '').upper()

        if not order_num:
            return Response('SUCCESS')

        try:
            trx = Transaction.objects.get(trx_id=order_num)
        except Transaction.DoesNotExist:
            return Response('SUCCESS')

        try:
            dep = Deposit.objects.get(order_num=order_num)
            dep.callback_payload = callback
            dep.callback_at = timezone.now()
            dep.save(update_fields=['callback_payload', 'callback_at'])
        except Deposit.DoesNotExist:
            pass

        if trx.status == 'COMPLETED':
            return Response('SUCCESS')

        success = status_val in ('SUCCESS', 'COMPLETED') or (code in ('00', '200') and msg in ('SUCCESS', 'OK'))
        if success:
            user = trx.user
            wallet_field = 'balance' if trx.wallet_type == 'BALANCE' else 'balance_deposit'
            with db_transaction.atomic():
                current_balance = getattr(user, wallet_field)
                setattr(user, wallet_field, current_balance + trx.amount)
                user.save(update_fields=[wallet_field])
                trx.status = 'COMPLETED'
                trx.save(update_fields=['status'])
                try:
                    dep = Deposit.objects.get(order_num=order_num)
                    dep.status = 'COMPLETED'
                    dep.save(update_fields=['status'])
                except Deposit.DoesNotExist:
                    pass
            return Response('SUCCESS')
        else:
            if trx.status in ('PENDING', 'PROCESSING'):
                trx.status = 'FAILED'
                trx.save(update_fields=['status'])
                try:
                    dep = Deposit.objects.get(order_num=order_num)
                    dep.status = 'FAILED'
                    dep.save(update_fields=['status'])
                except Deposit.DoesNotExist:
                    pass
            return Response('SUCCESS')


class DepositTransactionsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'transactions'

    @extend_schema(
        summary="Daftar transaksi Deposit",
        parameters=[
            OpenApiParameter(name='status', type=str, description='Filter status transaksi'),
            OpenApiParameter(name='wallet_type', type=str, description='Filter wallet (BALANCE/BALANCE_DEPOSIT)'),
            OpenApiParameter(name='start_date', type=str, description='Tanggal mulai (YYYY-MM-DD)'),
            OpenApiParameter(name='end_date', type=str, description='Tanggal akhir (YYYY-MM-DD)'),
            OpenApiParameter(name='gateway', type=str, description='Filter gateway (JAYAPAY/KLIKPAY)'),
            OpenApiParameter(name='order_num', type=str, description='Filter berdasarkan nomor order'),
        ],
        responses=TransactionSerializer(many=True),
        description='Mengambil daftar transaksi bertipe DEPOSIT untuk user saat ini atau semua jika admin.'
    )
    def get(self, request):
        # Base queryset: admin melihat semua; user melihat miliknya atau referral
        if request.user.is_staff:
            queryset = Transaction.objects.all()
        else:
            queryset = Transaction.objects.filter(Q(user=request.user) | Q(upline_user=request.user))
        
        # Optimize queries to avoid N+1
        queryset = queryset.select_related('user', 'product', 'upline_user').prefetch_related('related_withdrawal')

        # Hanya transaksi bertipe DEPOSIT
        queryset = queryset.filter(type='DEPOSIT')

        # Query params
        status_param = request.query_params.get('status')
        wallet_type = request.query_params.get('wallet_type')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        gateway = request.query_params.get('gateway')
        order_num = request.query_params.get('order_num')

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

        # Filter melalui relasi Deposit (gateway, order_num)
        if gateway or order_num:
            dep_qs = Deposit.objects.all() if request.user.is_staff else Deposit.objects.filter(user=request.user)
            if gateway:
                dep_qs = dep_qs.filter(gateway=gateway)
            if order_num:
                dep_qs = dep_qs.filter(order_num=order_num)
            queryset = queryset.filter(id__in=dep_qs.values_list('transaction_id', flat=True))

        serializer = TransactionSerializer(queryset, many=True)
        return Response(serializer.data)
