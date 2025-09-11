from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'accounts'

urlpatterns = [
    # Registration endpoints
    path('register/step1/validate/', views.register_step1_validate, name='register_step1_validate'),
    path('register/step2/validate/', views.register_step2_validate, name='register_step2_validate'),
    path('register/complete/', views.complete_registration, name='complete_registration'),
    
    # Authentication endpoints
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Profile endpoints
    # path('profile/', views.user_profile, name='profile'),
    # path('profile/update/', views.UserProfileView.as_view(), name='profile_update'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
]
