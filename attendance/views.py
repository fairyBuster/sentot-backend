from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import random
from .models import AttendanceSettings, AttendanceLog
from .models import AttendanceBonusClaim
from products.models import Transaction
import uuid
from .serializers import AttendanceSettingsSerializer, AttendanceLogSerializer
from zoneinfo import ZoneInfo


USER_TAG = "User API"
ADMIN_TAG = "Admin API"


class AttendanceSettingsViewSet(viewsets.ModelViewSet):
    queryset = AttendanceSettings.objects.all()
    serializer_class = AttendanceSettingsSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=[ADMIN_TAG],
        responses={
            200: OpenApiResponse(response=AttendanceSettingsSerializer(many=True), description='List attendance settings'),
        },
        description='List all attendance settings (admin-only for write operations)'
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=[USER_TAG],
        responses={
            200: OpenApiResponse(response=AttendanceSettingsSerializer, description='Get active attendance settings'),
            404: OpenApiResponse(description='No active settings found'),
        },
        description='Retrieve the currently active attendance settings'
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=[USER_TAG],
        responses={
            200: OpenApiResponse(response=AttendanceSettingsSerializer, description='Active attendance settings'),
            404: OpenApiResponse(description='No active settings found'),
        },
        description='Get the first active attendance settings'
    )
    @action(detail=False, methods=['get'], url_path='active')
    def get_active(self, request):
        settings = AttendanceSettings.objects.filter(is_active=True).order_by('-created_at').first()
        if not settings:
            return Response({'detail': 'No active settings found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AttendanceSettingsSerializer(settings).data)


class AttendanceLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AttendanceLogSerializer
    permission_classes = [IsAuthenticated]
    throttle_scope = 'attendance_claim'

    def get_queryset(self):
        # Users can only see their own logs; admin can see all
        qs = AttendanceLog.objects.select_related('user').all()
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        return qs

    @extend_schema(
        tags=[USER_TAG],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name='AttendanceStreakResponse',
                    fields={
                        'streak': serializers.IntegerField(),
                        'last_claim_date': serializers.DateField(allow_null=True),
                        'has_claimed_today': serializers.BooleanField(),
                        'can_claim_today': serializers.BooleanField(),
                        'next_claim_date': serializers.DateField(),
                        'cycle_days': serializers.IntegerField(allow_null=True),
                        'cycle_day': serializers.IntegerField(allow_null=True),
                    },
                ),
                description='Current attendance streak for authenticated user'
            )
        },
        description='Get current attendance streak for authenticated user.'
    )
    @action(detail=False, methods=['get'], url_path='streak')
    def streak(self, request):
        user = request.user
        local_zone = ZoneInfo('Asia/Jakarta')
        now_local = timezone.localtime(timezone.now(), local_zone)
        today = now_local.date()
        yesterday = today - timezone.timedelta(days=1)

        last_log = AttendanceLog.objects.filter(user=user).order_by('-date', '-created_at').first()
        last_claim_date = last_log.date if last_log else None

        has_claimed_today = bool(last_log and last_log.date == today)
        can_claim_today = not AttendanceLog.objects.filter(user=user, date=today).exists()

        streak_val = 0
        if last_log:
            if last_log.date in (today, yesterday):
                streak_val = int(last_log.streak_count or 0)

        settings_obj = AttendanceSettings.objects.filter(is_active=True).order_by('-created_at').first()
        cycle_days = None
        cycle_day = None
        if settings_obj and settings_obj.reward_type == 'daily' and streak_val > 0:
            cycle_days = int(settings_obj.daily_cycle_days or 0) if int(settings_obj.daily_cycle_days or 0) > 0 else 7
            cycle_day = (streak_val - 1) % cycle_days + 1

        return Response({
            'streak': streak_val,
            'last_claim_date': last_claim_date,
            'has_claimed_today': has_claimed_today,
            'can_claim_today': can_claim_today,
            'next_claim_date': today + timezone.timedelta(days=1),
            'cycle_days': cycle_days,
            'cycle_day': cycle_day,
        })

    @extend_schema(
        tags=[USER_TAG],
        responses={
            200: OpenApiResponse(
                response=AttendanceLogSerializer,
                description='Klaim absensi harian berhasil'
            ),
            400: OpenApiResponse(description='Sudah klaim hari ini atau konfigurasi tidak tersedia')
        },
        description='Klaim absensi harian. Hanya bisa sekali per hari per user.'
    )
    @action(detail=False, methods=['post'], url_path='claim')
    def claim(self, request):
        user = request.user
        # Gunakan tanggal lokal Asia/Jakarta agar batas hari mengikuti waktu Indonesia
        local_zone = ZoneInfo('Asia/Jakarta')
        now_local = timezone.localtime(timezone.now(), local_zone)
        today = now_local.date()

        # Cek sudah klaim hari ini
        if AttendanceLog.objects.filter(user=user, date=today).exists():
            return Response({'error': 'Anda sudah klaim absensi hari ini.'}, status=status.HTTP_400_BAD_REQUEST)

        # Ambil setting aktif
        settings = AttendanceSettings.objects.filter(is_active=True).order_by('-created_at').first()
        if not settings:
            return Response({'error': 'Konfigurasi attendance tidak tersedia.'}, status=status.HTTP_400_BAD_REQUEST)

        # Hitung streak
        last_log = AttendanceLog.objects.filter(user=user).order_by('-date').first()
        yesterday = today - timezone.timedelta(days=1)
        if last_log and last_log.date == yesterday:
            streak = last_log.streak_count + 1
        else:
            streak = 1

        # Tentukan reward dasar berdasarkan reward_type
        rt = settings.reward_type
        cycle_days_for_bonus = None
        cycle_day_for_bonus = None
        if rt == 'fixed':
            base_amount = Decimal(settings.fixed_amount or 0)
        elif rt == 'random':
            min_amt = Decimal(settings.min_amount or 0)
            max_amt = Decimal(settings.max_amount or 0)
            if max_amt < min_amt:
                max_amt = min_amt
            rand_float = random.uniform(float(min_amt), float(max_amt))
            base_amount = Decimal(str(rand_float)).quantize(Decimal('0.01'))
        elif rt == 'rank':
            # Gunakan user.rank sebagai key '1'..'6'
            rank_key = str(user.rank or '').strip()
            amount_from_rank = None
            if rank_key:
                try:
                    amount_from_rank = Decimal(str(settings.rank_rewards.get(rank_key, 0)))
                except Exception:
                    amount_from_rank = Decimal('0')
            # Fallback jika rank tidak tersedia atau tidak terkonfigurasi
            base_amount = amount_from_rank if amount_from_rank and amount_from_rank > 0 else Decimal(settings.fixed_amount or 0)
        elif rt == 'daily':
            # Calculate day in cycle (1-based)
            cycle_days = settings.daily_cycle_days if settings.daily_cycle_days > 0 else 7
            cycle_day = (streak - 1) % cycle_days + 1
            cycle_days_for_bonus = cycle_days
            cycle_day_for_bonus = cycle_day
            cycle_key = str(cycle_day)
            
            try:
                base_amount = Decimal(str(settings.daily_rewards.get(cycle_key, 0)))
            except Exception:
                base_amount = Decimal('0')
                
            # Fallback if 0
            if base_amount <= 0:
                base_amount = Decimal(settings.fixed_amount or 0)
        else:
            # Default fallback bila reward_type tidak dikenali
            base_amount = Decimal(settings.fixed_amount or 0)

        # Bonus streak
        bonus = Decimal('0')
        if settings.consecutive_bonus_enabled:
            if rt == 'daily':
                if cycle_days_for_bonus and cycle_day_for_bonus and cycle_day_for_bonus == cycle_days_for_bonus:
                    if settings.bonus_7_days:
                        if not settings.bonus_claim_separate_enabled:
                            bonus += Decimal(settings.bonus_7_days)
            else:
                if streak == 7 and settings.bonus_7_days:
                    if not settings.bonus_claim_separate_enabled:
                        bonus += Decimal(settings.bonus_7_days)
                if streak == 30 and settings.bonus_30_days:
                    if not settings.bonus_claim_separate_enabled:
                        bonus += Decimal(settings.bonus_30_days)

        total_amount = (base_amount + bonus).quantize(Decimal('0.01'))

        # Tentukan sumber saldo sesuai konfigurasi
        balance_field = 'balance' if settings.balance_source == 'balance' else 'balance_deposit'
        wallet_type = 'BALANCE' if balance_field == 'balance' else 'BALANCE_DEPOSIT'

        with transaction.atomic():
            # Tambahkan reward ke sumber saldo yang dipilih
            current_balance = getattr(user, balance_field)
            setattr(user, balance_field, current_balance + total_amount)
            user.save()

            # Simpan log
            log = AttendanceLog.objects.create(
                user=user,
                date=today,
                streak_count=streak,
                amount=total_amount,
            )

            # Catat transaksi kredit ke tabel transactions
            trx_id = f'ATT-{timezone.now().strftime("%Y%m%d%H%M%S")}-{uuid.uuid4().hex[:6].upper()}'
            attendance_tx = Transaction.objects.create(
                user=user,
                product=None,
                type='ATTENDANCE',
                amount=total_amount,
                description='Daily attendance claim',
                status='COMPLETED',
                wallet_type=wallet_type,
                trx_id=trx_id
            )

        return Response({
            'message': 'Klaim absensi berhasil',
            'claimed_amount': str(total_amount),
            'streak': streak,
            'balance_type': settings.balance_source,
            'balance_after': str(getattr(user, balance_field)),
            'next_claim_date': str(today + timezone.timedelta(days=1)),
            'log': AttendanceLogSerializer(log).data,
            'transaction_id': attendance_tx.trx_id
        })

    @extend_schema(
        tags=[USER_TAG],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name='AttendanceClaimBonusResponse',
                    fields={
                        'message': serializers.CharField(),
                        'bonus_type': serializers.CharField(),
                        'claimed_amount': serializers.CharField(),
                        'streak': serializers.IntegerField(),
                        'cycle_days': serializers.IntegerField(allow_null=True),
                        'cycle_index': serializers.IntegerField(allow_null=True),
                        'balance_type': serializers.CharField(),
                        'balance_after': serializers.CharField(),
                        'transaction_id': serializers.CharField(),
                    },
                ),
                description='Attendance bonus claimed successfully'
            ),
            400: OpenApiResponse(description='Bonus tidak bisa diklaim / sudah diklaim / belum memenuhi syarat'),
        },
        description='Klaim bonus beruntun secara terpisah (harus sudah claim attendance hari ini).'
    )
    @action(detail=False, methods=['post'], url_path='claim-bonus')
    def claim_bonus(self, request):
        user = request.user
        local_zone = ZoneInfo('Asia/Jakarta')
        now_local = timezone.localtime(timezone.now(), local_zone)
        today = now_local.date()

        settings_obj = AttendanceSettings.objects.filter(is_active=True).order_by('-created_at').first()
        if not settings_obj:
            return Response({'error': 'Konfigurasi attendance tidak tersedia.'}, status=status.HTTP_400_BAD_REQUEST)
        if not settings_obj.consecutive_bonus_enabled:
            return Response({'error': 'Bonus beruntun tidak aktif.'}, status=status.HTTP_400_BAD_REQUEST)
        if not settings_obj.bonus_claim_separate_enabled:
            return Response({'error': 'Mode klaim bonus terpisah tidak aktif.'}, status=status.HTTP_400_BAD_REQUEST)

        last_log = AttendanceLog.objects.filter(user=user).order_by('-date', '-created_at').first()
        if not last_log or last_log.date != today:
            return Response({'error': 'Bonus hanya bisa diklaim setelah klaim attendance hari ini.'}, status=status.HTTP_400_BAD_REQUEST)

        streak = int(last_log.streak_count or 0)
        if streak <= 0:
            return Response({'error': 'Streak tidak valid.'}, status=status.HTTP_400_BAD_REQUEST)

        bonus_type = None
        amount = Decimal('0')
        cycle_days = None
        cycle_index = None

        if settings_obj.reward_type == 'daily':
            cycle_days = int(settings_obj.daily_cycle_days or 0) if int(settings_obj.daily_cycle_days or 0) > 0 else 7
            if streak % cycle_days != 0:
                return Response({'error': f'Bonus hanya bisa diklaim saat mencapai hari terakhir siklus (Day {cycle_days}).'}, status=status.HTTP_400_BAD_REQUEST)
            cycle_index = streak // cycle_days
            bonus_type = 'cycle'
            amount = Decimal(settings_obj.bonus_7_days or 0)
            if amount <= 0:
                return Response({'error': 'Bonus siklus belum diset atau bernilai 0.'}, status=status.HTTP_400_BAD_REQUEST)
            if AttendanceBonusClaim.objects.filter(user=user, bonus_type='cycle', cycle_index=cycle_index).exists():
                return Response({'error': 'Bonus siklus untuk periode ini sudah diklaim.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if streak == 7:
                bonus_type = 'streak_7'
                amount = Decimal(settings_obj.bonus_7_days or 0)
                if amount <= 0:
                    return Response({'error': 'Bonus 7 hari belum diset atau bernilai 0.'}, status=status.HTTP_400_BAD_REQUEST)
            elif streak == 30:
                bonus_type = 'streak_30'
                amount = Decimal(settings_obj.bonus_30_days or 0)
                if amount <= 0:
                    return Response({'error': 'Bonus 30 hari belum diset atau bernilai 0.'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'error': 'Belum mencapai milestone bonus (7/30 hari).'}, status=status.HTTP_400_BAD_REQUEST)

            if AttendanceBonusClaim.objects.filter(user=user, bonus_type=bonus_type).exists():
                return Response({'error': 'Bonus milestone ini sudah diklaim.'}, status=status.HTTP_400_BAD_REQUEST)

        balance_field = 'balance' if settings_obj.balance_source == 'balance' else 'balance_deposit'
        wallet_type = 'BALANCE' if balance_field == 'balance' else 'BALANCE_DEPOSIT'

        with transaction.atomic():
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user_locked = User.objects.select_for_update().get(id=user.id)
            current_balance = getattr(user_locked, balance_field)
            setattr(user_locked, balance_field, current_balance + amount)
            user_locked.save(update_fields=[balance_field])

            AttendanceBonusClaim.objects.create(
                user=user_locked,
                bonus_type=bonus_type,
                claimed_for_streak=streak,
                cycle_index=cycle_index,
                amount=amount
            )

            trx_id = f'ATB-{timezone.now().strftime("%Y%m%d%H%M%S")}-{uuid.uuid4().hex[:6].upper()}'
            tx = Transaction.objects.create(
                user=user_locked,
                product=None,
                type='ATTENDANCE',
                amount=amount,
                description='Attendance bonus claim',
                status='COMPLETED',
                wallet_type=wallet_type,
                trx_id=trx_id
            )

        return Response({
            'message': 'Klaim bonus berhasil',
            'bonus_type': bonus_type,
            'claimed_amount': str(amount.quantize(Decimal('0.01'))),
            'streak': streak,
            'cycle_days': cycle_days,
            'cycle_index': cycle_index,
            'balance_type': settings_obj.balance_source,
            'balance_after': str(getattr(user_locked, balance_field)),
            'transaction_id': tx.trx_id
        })
