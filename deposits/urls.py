from django.urls import path
from .views import (
    JayapayDepositInitiateView,
    JayapayDepositCallbackView,
    KlikpayDepositInitiateView,
    KlikpayDepositCallbackView,
    DepositTransactionsListView,
)

urlpatterns = [
    path('jayapay/initiate/', JayapayDepositInitiateView.as_view(), name='deposit-jayapay-initiate'),
    path('jayapay/callback/', JayapayDepositCallbackView.as_view(), name='deposit-jayapay-callback'),
    path('klikpay/initiate/', KlikpayDepositInitiateView.as_view(), name='deposit-klikpay-initiate'),
    path('klikpay/callback/', KlikpayDepositCallbackView.as_view(), name='deposit-klikpay-callback'),
    path('transactions/', DepositTransactionsListView.as_view(), name='deposit-transactions-list'),
]