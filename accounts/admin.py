from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, BusinessProfile

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'phone_number', 'is_active', 'date_joined')
    list_filter = ('role', 'is_email_verified', 'is_staff', 'is_2fa_enabled')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    ordering = ('-date_joined',)
    filter_horizontal = ('groups', 'user_permissions',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {
            'fields': ('first_name', 'last_name', 'role', 'phone_number', 'language')
        }),
        ('Permissions', {
            'fields': ('is_email_verified', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('2FA', {'fields': ('is_2fa_enabled', 'totp_secret')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'first_name', 'last_name', 'password1', 'password2', 'role',
                'phone_number', 'language'
            ),
        }),
    )


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'kvk_number', 'legal_form', 'user', 'status_flag', 'created_at')
    list_filter = ('legal_form', 'reporting_period', 'status_flag')
    search_fields = ('company_name', 'kvk_number', 'user__email', 'user__first_name', 'user__last_name')
    readonly_fields = ('created_at', 'updated_at')
