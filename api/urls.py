# api/urls.py - Make sure this is your complete URL configuration

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.views import (
    transactions_views, 
    bank_account_views, 
    category_views, 
    receipts_views, 
    vat_returns_views,
    dashboard_views
)

# Create router and register viewsets
router = DefaultRouter()

# Register all viewsets
router.register(r'transactions', transactions_views.TransactionViewSet, basename='transaction')
router.register(r'accounts', bank_account_views.AccountViewSet, basename='account')
router.register(r'categories', category_views.CategoryViewSet, basename='category')
router.register(r'receipts', receipts_views.ReceiptViewSet, basename='receipt')
router.register(r'vat-returns', vat_returns_views.VATReturnViewSet, basename='vatreturn')
# router.register(r'vat-line-items', vat_returns_views.VATReturnLineItemViewSet, basename='vatreturnlineitem')
router.register(r'dashboard', dashboard_views.DashboardViewSet, basename='dashboard')

urlpatterns = [
    path('', include(router.urls)),
]

# Debug: Print registered URLs (remove in production)
# Run this in Django shell to see all URLs:
# from django.urls import reverse
# print("Available VAT return URLs:")
# print("List:", reverse('vatreturn-list'))
# print("Available periods:", reverse('vatreturn-available-periods'))
# print("Current period:", reverse('vatreturn-current-period'))
# print("Statistics:", reverse('vatreturn-statistics'))