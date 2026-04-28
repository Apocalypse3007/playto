from django.urls import path
from .views import MerchantDashboardView, PayoutRequestView, SettlePayoutView, MerchantCreateView

urlpatterns = [
    path('merchants', MerchantCreateView.as_view(), name='create_merchant'),
    path('merchants/<uuid:merchant_id>/dashboard', MerchantDashboardView.as_view(), name='dashboard'),
    path('merchants/<uuid:merchant_id>/payouts', PayoutRequestView.as_view(), name='payout_request'),
    path('payouts/<uuid:payout_id>/settle', SettlePayoutView.as_view(), name='settle_payout'),
]
