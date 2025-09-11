from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login
from django.db import transaction
from .models import User, BusinessProfile
from .serializers import (
    UserRegistrationStep1Serializer,
    UserRegistrationStep2Serializer,
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

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_step2_validate(request):
    """
    Validate step 2 registration data (business profile)
    """
    serializer = UserRegistrationStep2Serializer(data=request.data)
    if serializer.is_valid():
        return Response({
            'message': 'Step 2 validation successful',
            'data': serializer.validated_data
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    User login endpoint
    """
    serializer = UserLoginSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        user = serializer.validated_data['user']
        login(request, user)
        
        # Generate JWT tokens
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

# @api_view(['GET'])
# def user_profile(request):
#     """
#     Get current user profile
#     """
#     serializer = UserProfileSerializer(request.user)
#     return Response(serializer.data)
