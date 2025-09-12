import random
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login
from django.db import transaction
from django.core.mail import send_mail
from .models import OTPVerification, User
from .serializers import (
    UserRegistrationStep1Serializer,
    CompleteRegistrationSerializer,
    UserLoginSerializer,
    UserProfileSerializer
)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_step1_validate(request):
    """
    Validate step 1 registration data without creating user
    """
    serializer = UserRegistrationStep1Serializer(data=request.data)
    if serializer.is_valid():
        return Response({
            'message': 'Step 1 validation successful',
            'data': {
                'first_name': serializer.validated_data['first_name'],
                'last_name': serializer.validated_data['last_name'],
                'email': serializer.validated_data['email']
            }
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Add after register_step1_validate view:
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def send_verification_email(request):
    email = request.data.get('email')
    try:
        user = User.objects.get(email=email, is_email_verified=False)
        verification_link = f"http://localhost:3000/verify-email/{user.email_verification_token}"
        send_mail(
            'Verify your email',
            f'Click here to verify: {verification_link}',
            'noreply@yourdomain.com',
            [user.email]
        )
        return Response({'message': 'Verification email sent'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=400)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def verify_email(request):
    token = request.data.get('token')
    try:
        user = User.objects.get(email_verification_token=token)
        user.is_email_verified = True
        user.is_active = True
        user.email_verification_token = None
        user.save()
        return Response({'message': 'Email verified successfully'})
    except User.DoesNotExist:
        return Response({'error': 'Invalid token'}, status=400)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def complete_registration(request):
    """
    Complete user registration with both user and business profile data
    """
    serializer = CompleteRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        try:
            with transaction.atomic():
                user = serializer.save()               
                user.is_active = False  
                # Generate JWT tokens
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'message': 'Registration successful',
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'role': user.role,
                        'business_profile': {
                            'company_name': user.business_profile.company_name,
                            'kvk_number': user.business_profile.kvk_number,
                            'legal_form': user.business_profile.legal_form,
                            'reporting_period': user.business_profile.reporting_period,
                        }
                    },
                    'tokens': {
                        'access': str(refresh.access_token),
                        'refresh': str(refresh)
                    }
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'error': 'Registration failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def user_login(request):
    """
    User login endpoint with 2FA support
    """
    serializer = UserLoginSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Check if email is verified
        if not user.is_email_verified:
            return Response({
                'error': 'Please verify your email before logging in',
                'email_not_verified': True
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if 2FA is enabled
        if user.is_2fa_enabled:
            # Generate and send OTP
            otp_code = str(random.randint(100000, 999999))
            OTPVerification.objects.filter(user=user, is_verified=False).delete()
            OTPVerification.objects.create(user=user, otp_code=otp_code)
            # Send OTP via email
            send_mail(
                'Your Login OTP',
                f'Your OTP code is: {otp_code}',
                'noreply@yourdomain.com',
                [user.email],
                fail_silently=False,
            )
            
            return Response({
                'message': 'OTP sent to your email',
                'user_id': user.id,
                'requires_2fa': True,
                'email': user.email
            }, status=status.HTTP_200_OK)
        
        # Normal login without 2FA
        login(request, user)
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.full_name,
                'role': user.role,
                'is_2fa_enabled': user.is_2fa_enabled,
            },
            'tokens': {
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            }
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def verify_otp(request):
    user_id = request.data.get('user_id')
    otp_code = request.data.get('otp_code')
    
    try:
        otp_obj = OTPVerification.objects.get(user_id=user_id, otp_code=otp_code, is_verified=False)
        if otp_obj.is_expired():
            return Response({'error': 'OTP expired'}, status=400)
        
        otp_obj.is_verified = True
        otp_obj.save()
        
        refresh = RefreshToken.for_user(otp_obj.user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {'id': otp_obj.user.id, 'email': otp_obj.user.email}
        })
    except OTPVerification.DoesNotExist:
        return Response({'error': 'Invalid OTP'}, status=400)
@api_view(['POST'])
def user_logout(request):
    """
    User logout endpoint
    """
    try:
        refresh_token = request.data.get('refresh_token')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
    except Exception:
        return Response({'error': 'Invalid refresh token'}, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and update user profile
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

