# transaction/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router and register viewsets
router = DefaultRouter()
router.register(r'transactions', views.TransactionViewSet, basename='transaction')
router.register(r'accounts', views.AccountViewSet, basename='account')
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'receipts', views.ReceiptViewSet, basename='receipt')
router.register(r'imports', views.TransactionImportViewSet, basename='import')

app_name = 'transactions'

urlpatterns = [
    # Router URLs for viewsets
    path('', include(router.urls)),
    
    # Additional custom endpoints
    path('dashboard/stats/', views.DashboardStatsView.as_view(), name='dashboard-stats'),
]

# Your main project urls.py is already correctly configured:
# path('api/transaction/', include('transaction.urls'))

# This will create URLs like:
# /api/transaction/transactions/
# /api/transaction/accounts/
# /api/transaction/categories/
# /api/transaction/receipts/
# /api/transaction/imports/
# /api/transaction/dashboard/stats/