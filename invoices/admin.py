# invoices/admin.py

from django.contrib import admin
from .models import Customer, Invoice, InvoiceLine, InvoiceEmailLog

class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1
    readonly_fields = ['line_total', 'vat_amount']

class InvoiceEmailLogInline(admin.TabularInline):
    model = InvoiceEmailLog
    extra = 0
    readonly_fields = ['sent_at', 'sent_successfully']

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'vat_number', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'vat_number', 'user__email']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'user', 'customer', 'invoice_date', 'total', 'status', 'is_overdue']
    list_filter = ['status', 'invoice_date', 'due_date', 'created_at']
    search_fields = ['invoice_number', 'customer__name', 'user__email']
    readonly_fields = ['subtotal', 'total_vat', 'total', 'vat_breakdown', 'is_overdue', 'created_at', 'updated_at']
    inlines = [InvoiceLineInline, InvoiceEmailLogInline]
    
    fieldsets = (
        ('Invoice Details', {
            'fields': ('invoice_number', 'invoice_date', 'due_date', 'customer', 'status')
        }),
        ('Company Information', {
            'fields': ('company_name', 'company_address', 'company_vat_number', 'company_chamber_of_commerce', 'company_logo'),
            'classes': ['collapse']
        }),
        ('Totals', {
            'fields': ('subtotal', 'total_vat', 'total', 'vat_breakdown'),
            'classes': ['collapse']
        }),
        ('Additional Information', {
            'fields': ('notes', 'payment_instructions'),
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ('sent_at', 'paid_at', 'created_at', 'updated_at'),
            'classes': ['collapse']
        })
    )

@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'description', 'quantity', 'unit_price', 'vat_rate', 'line_total']
    list_filter = ['vat_rate', 'created_at']
    search_fields = ['description', 'invoice__invoice_number']
    readonly_fields = ['line_total', 'vat_amount']

@admin.register(InvoiceEmailLog)
class InvoiceEmailLogAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'to_email', 'sent_successfully', 'sent_at']
    list_filter = ['sent_successfully', 'sent_at']
    search_fields = ['to_email', 'invoice__invoice_number']
    readonly_fields = ['sent_at']
