from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User, BusinessProfile

class UserRegistrationStep1Serializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=30)
    last_name = serializers.CharField(max_length=30)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        existing_user = User.objects.filter(email=value).first()
        if existing_user:
            if not existing_user.is_email_verified:
                existing_user.delete()
            else:
                raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Password and confirm password do not match.")
        return attrs

class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = ['company_name', 'kvk_number', 'legal_form', 'reporting_period',
            'vat_number', 'address', 'postal_code', 'city', 'accounting_year',]

    def validate_kvk_number(self, value):
        # Basic KVK number validation (8 digits)
        if not value.isdigit() or len(value) != 8:
            raise serializers.ValidationError("KVK number must be exactly 8 digits.")
        return value

class CompleteRegistrationSerializer(serializers.Serializer):
    # Step 1 fields
    first_name = serializers.CharField(max_length=30)
    last_name = serializers.CharField(max_length=30)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    
    # Step 2 fields
    company_name = serializers.CharField(max_length=200)
    kvk_number = serializers.CharField(max_length=8)
    legal_form = serializers.ChoiceField(choices=BusinessProfile.LEGAL_FORM_CHOICES)
    reporting_period = serializers.ChoiceField(choices=BusinessProfile.REPORTING_PERIOD_CHOICES, default='quarter')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_kvk_number(self, value):
        if not value.isdigit() or len(value) != 8:
            raise serializers.ValidationError("KVK number must be exactly 8 digits.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Password and confirm password do not match.")
        return attrs

    def create(self, validated_data):
        # Remove confirm_password from validated_data
        validated_data.pop('confirm_password')
        
        # Extract business profile data
        business_data = {
            'company_name': validated_data.pop('company_name'),
            'kvk_number': validated_data.pop('kvk_number'),
            'legal_form': validated_data.pop('legal_form'),
            'reporting_period': validated_data.pop('reporting_period'),
        }
        
        # Create user
        user = User.objects.create_user(**validated_data)
        
        # Create business profile
        BusinessProfile.objects.create(user=user, **business_data)
        
        return user

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(request=self.context.get('request'),
                              username=email, password=password)
            
            if not user:
                raise serializers.ValidationError('Invalid email or password.')
            
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled.')
            
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError('Must include email and password.')

class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)
    confirm_password = serializers.CharField(required=True)
    
    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("New passwords do not match")
        return data

class UserProfileSerializer(serializers.ModelSerializer):
    business_profile = BusinessProfileSerializer()
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'role',
            'date_joined',
            'is_2fa_enabled',
            'phone_number',  
            'language',      
            'business_profile',
        ]
        read_only_fields = [
            'id',
            'email',
            'date_joined',
            'role',
        ]
    def update(self, instance, validated_data):
        # 🔹 Pop business_profile data if present
        business_data = validated_data.pop("business_profile", None)

        # Update User fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update BusinessProfile
        if business_data:
            business_profile = instance.business_profile  # one-to-one relation
            for attr, value in business_data.items():
                setattr(business_profile, attr, value)
            business_profile.save()

        return instance
