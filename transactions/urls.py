# transaction/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .Views import views

# Create router and register viewsets
router = DefaultRouter()
router.register(r'transactions', views.TransactionViewSet, basename='transaction')
router.register(r'accounts', views.AccountViewSet, basename='account')
router.register(r'categories', views.CategoryViewSet, basename='category')
# router.register(r'receipts', views.ReceiptViewSet, basename='receipt')
# router.register(r'imports', views.TransactionImportViewSet, basename='import')


urlpatterns = [
    path('', include(router.urls)),    
   
]
