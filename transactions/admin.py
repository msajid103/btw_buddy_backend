from django.contrib import admin
from .models import Account, Category, Transaction,TransactionImport


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'account_number', 'bank_name', 'is_active', 'created_at')
    list_filter = ('is_active', 'bank_name')
    search_fields = ('name', 'account_number', 'user__email', 'user__full_name')
    ordering = ('-created_at',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'category_type', 'color', 'is_active', 'created_at')
    list_filter = ('category_type', 'is_active')
    search_fields = ('name', 'user__email', 'user__full_name')
    ordering = ('-created_at',)




@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'account', 'category', 'date', 'description',
        'amount', 'transaction_type', 'vat_amount', 'status',
        'has_receipt', 'created_at'
    )
    list_filter = ('transaction_type', 'status', 'has_receipt', 'date')
    search_fields = (
        'description', 'reference_number',
        'user__email', 'user__full_name',
        'account__name', 'category__name'
    )
    ordering = ('-date', '-created_at')
    readonly_fields = ('created_at', 'updated_at', 'import_reference')




@admin.register(TransactionImport)
class TransactionImportAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'filename', 'status',
        'total_rows', 'processed_rows', 'successful_rows', 'failed_rows',
        'created_at', 'completed_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('filename', 'user__email', 'user__full_name')
    ordering = ('-created_at',)
    readonly_fields = ('error_log', 'created_at', 'completed_at')
