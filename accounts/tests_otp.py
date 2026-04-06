from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import GeneralSetting, PhoneOTP
from unittest.mock import patch

class OTPTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.setting = GeneralSetting.objects.create(
            otp_enabled=True,
            verifyway_api_key='test_key',
            whatsapp_check_enabled=False,
            checknumber_api_key=''
        )

    @patch('accounts.views.send_whatsapp_otp')
    def test_request_otp_success(self, mock_send):
        mock_send.return_value = (True, "OTP sent successfully")
        response = self.client.post('/api/auth/request-otp/', {'phone': '08123456789'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(PhoneOTP.objects.filter(phone='08123456789').exists())
        
    def test_otp_disabled(self):
        self.setting.otp_enabled = False
        self.setting.save()
        response = self.client.post('/api/auth/request-otp/', {'phone': '08123456789'})
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @patch('accounts.views.send_whatsapp_otp')
    def test_register_with_otp(self, mock_send):
        # 1. Request OTP
        mock_send.return_value = (True, "OTP sent successfully")
        self.client.post('/api/auth/request-otp/', {'phone': '08123456789'})
        otp = PhoneOTP.objects.get(phone='08123456789').otp_code
        
        # 2. Register
        data = {
            'username': 'newuser',
            'phone': '08123456789',
            'password': 'StrongPassword123!',
            'password2': 'StrongPassword123!',
            'email': 'new@example.com',
            'full_name': 'New User',
            'otp': otp
        }
        response = self.client.post('/api/auth/register/', data)
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Registration failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # OTP should be deleted
        self.assertFalse(PhoneOTP.objects.filter(phone='08123456789').exists())

    @patch('accounts.views.send_whatsapp_otp')
    def test_register_fail_invalid_otp(self, mock_send):
        # 1. Request OTP
        mock_send.return_value = (True, "OTP sent successfully")
        self.client.post('/api/auth/request-otp/', {'phone': '08123456789'})
        
        # 2. Register with wrong OTP
        data = {
            'username': 'newuser',
            'phone': '08123456789',
            'password': 'StrongPassword123!',
            'password2': 'StrongPassword123!',
            'email': 'new@example.com',
            'full_name': 'New User',
            'otp': '000000'
        }
        response = self.client.post('/api/auth/register/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('otp', response.data)

    @patch('accounts.views.check_whatsapp_registered')
    @patch('accounts.views.send_whatsapp_otp')
    def test_register_fallback_whatsapp_check_when_otp_missing(self, mock_send, mock_check):
        # Enable both OTP and WhatsApp check
        self.setting.otp_enabled = True
        self.setting.whatsapp_check_enabled = True
        self.setting.checknumber_api_key = 'dummy'
        self.setting.save()

        mock_send.return_value = (True, "OTP sent successfully")
        mock_check.return_value = (True, "Phone has active WhatsApp")

        data = {
            'username': 'userfallback',
            'phone': '08111111111',
            'password': 'StrongPassword123!',
            'password2': 'StrongPassword123!',
            'email': 'fallback@example.com',
            'full_name': 'User Fallback',
        }
        response = self.client.post('/api/auth/register/', data)
        # Fallback aktif: tanpa OTP tapi WA active -> sukses
        if response.status_code != status.HTTP_201_CREATED:
            print("Fallback register failed:", response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertGreaterEqual(mock_check.call_count, 1)

    @patch('accounts.views.check_whatsapp_registered')
    def test_register_with_whatsapp_check_only(self, mock_check):
        # OTP off, WhatsApp check on
        self.setting.otp_enabled = False
        self.setting.whatsapp_check_enabled = True
        self.setting.checknumber_api_key = 'dummy'
        self.setting.save()

        mock_check.return_value = (True, "Phone has active WhatsApp")

        data = {
            'username': 'userwa',
            'phone': '08123450000',
            'password': 'StrongPassword123!',
            'password2': 'StrongPassword123!',
            'email': 'userwa@example.com',
            'full_name': 'User WA',
        }
        response = self.client.post('/api/auth/register/', data)
        if response.status_code != status.HTTP_201_CREATED:
            print("WA check only register failed:", response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_check.assert_called_once()
