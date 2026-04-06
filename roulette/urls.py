from django.urls import path
from .views import RouletteStatusView, RouletteSpinView


urlpatterns = [
    path("status/", RouletteStatusView.as_view(), name="roulette-status"),
    path("spin/", RouletteSpinView.as_view(), name="roulette-spin"),
]

