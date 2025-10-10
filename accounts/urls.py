from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'accounts'

urlpatterns = [
    # Registration endpoints
    path('register/step1/validate/', views.register_step1_validate, name='register_step1_validate'),
    path('register/complete/', views.complete_registration, name='complete_registration'),
    
    # Authentication endpoints
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),   
    
    path('send-verification-email/', views.send_verification_email, name='send_verification_email'),
    path('verify-email/', views.verify_email, name='verify_email'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    path('change-password/', views.change_password, name='change_password'),

     # Password Reset URLs
    path('password-reset/', views.password_reset_request, name='password-reset-request'),
    path('password-reset-confirm/', views.password_reset_confirm, name='password-reset-confirm'),
    path('password-reset-validate/<str:uid>/<str:token>/', views.password_reset_validate_token, name='password-reset-validate'),

]
