from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('admin', 'Admin'),
        ('office', 'Office User'),
    ]

    LANGUAGE_CHOICES = [
        ('nl', 'Dutch'),
        ('en', 'English'),
        ('de', 'German'),
    ]

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    
    # 2FA fields (for future implementation)

    is_2fa_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=32, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, default="---------------")
    language =  models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='en')       
    
    
    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'auth_user'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

class BusinessProfile(models.Model):
    LEGAL_FORM_CHOICES = [
        ('zzp', 'Sole Proprietorship'),
        ('bv', 'Private Limited Company (B.V.)'),
        ('nv', 'Public Limited Company (N.V.)'),
        ('vof', 'General Partnership (V.O.F.)'),
        ('cv', 'Limited Partnership (C.V.)'),
        ('foundation', 'Foundation'),
        ('association', 'Association'),
    ]

    REPORTING_PERIOD_CHOICES = [
        ('month', 'Monthly'),
        ('quarter', 'Quarterly'),
        ('year', 'Yearly'),
    ]

    ACCOUNTING_YEAR_CHOICES = [
        ('calendar', 'Calendar Year (Jan–Dec)'),
        ('fiscal', 'Fiscal Year (Custom)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='business_profile')
    company_name = models.CharField(max_length=200)
    kvk_number = models.CharField(max_length=8, help_text="Dutch Chamber of Commerce number")
    legal_form = models.CharField(max_length=20, choices=LEGAL_FORM_CHOICES)
    reporting_period = models.CharField(max_length=10, choices=REPORTING_PERIOD_CHOICES, default='quarter')
    
    # Additional fields for future use
    address = models.TextField(blank=True,  default="---------------")
    phone = models.CharField(max_length=20, blank=True,  default="---------------")  
    vat_number = models.CharField(max_length=20, blank=True,  default="---------------")
    postal_code = models.CharField(max_length=20, blank=True,  default="---------------")
    city = models.CharField(max_length=100, blank=True, default="---------------")
    country = models.CharField(max_length=100, blank=True, default="---------------")

  
    accounting_year = models.CharField(
        max_length=20,
        choices=ACCOUNTING_YEAR_CHOICES,
        default='calendar'
    )

    
    # Settings
    status_flag = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_profiles'

    def __str__(self):
        return f"{self.company_name} - {self.user.full_name}"
