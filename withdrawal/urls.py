from django.urls import path
from .views import (
    WithdrawalListCreateView,
    WithdrawalSettingsView,
    WithdrawalServiceListView,
    JayapayInitiateView,
    JayapayCallbackView,
    WithdrawalTransactionsListView,
)

urlpatterns = [
    path('', WithdrawalListCreateView.as_view(), name='withdrawal-list-create'),
    path('settings/', WithdrawalSettingsView.as_view(), name='withdrawal-settings'),
    path('services/', WithdrawalServiceListView.as_view(), name='withdrawal-services'),
    path('jayapay/initiate/<int:pk>/', JayapayInitiateView.as_view(), name='withdrawal-jayapay-initiate'),
    path('jayapay/callback/', JayapayCallbackView.as_view(), name='withdrawal-jayapay-callback'),
    path('transactions/', WithdrawalTransactionsListView.as_view(), name='withdrawal-transactions'),
]
