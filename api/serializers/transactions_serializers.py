from rest_framework import serializers
from transactions.models import Transaction, TransactionImport

class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    formatted_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'date', 'description', 'amount', 'formatted_amount', 'transaction_type', 
           'vat_rate', 'vat_amount', 'status', 'has_receipt', 'account', 'account_name', 
            'category', 'category_name','reference_number', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'transaction_type', 'has_receipt', 'created_at', 'updated_at','vat_amount']
    
    def get_formatted_amount(self, obj):
        """Format amount with proper sign for display"""
        amount = abs(obj.amount)
        formatted = f"€{amount:,.2f}"
        return f"-{formatted}" if obj.amount < 0 else f"+{formatted}"
    
    def validate_account(self, value):
        """Ensure account belongs to the current user"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            if value.user != request.user:
                raise serializers.ValidationError("Account does not belong to the current user.")
        return value
    
    def validate_category(self, value):
        """Ensure category belongs to the current user and is appropriate for transaction type"""
        if value is None:
            return value
            
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            if value.user != request.user:
                raise serializers.ValidationError("Category does not belong to the current user.")
        return value


class TransactionBulkActionSerializer(serializers.Serializer):
    """Serializer for bulk actions on transactions"""
    ACTION_CHOICES = [
        ('label', 'Label transactions'),
        ('delete', 'Delete transactions'),
        ('change_category', 'Change category'),
        ('change_status', 'Change status'),
        ('export', 'Export transactions'),
    ]
    
    transaction_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of transaction IDs to perform action on"
    )
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    
    # Optional fields for specific actions
    category_id = serializers.IntegerField(required=False)
    status = serializers.ChoiceField(choices=Transaction.STATUS_CHOICES, required=False)
    
    def validate(self, data):
        action = data.get('action')
        
        if action == 'change_category' and not data.get('category_id'):
            raise serializers.ValidationError("category_id is required for change_category action")
        
        if action == 'change_status' and not data.get('status'):
            raise serializers.ValidationError("status is required for change_status action")
        
        return data


class TransactionImportSerializer(serializers.ModelSerializer):
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = TransactionImport
        fields = [
            'id', 'filename', 'total_rows', 'processed_rows', 'successful_rows', 
            'failed_rows', 'status', 'progress_percentage', 'error_log', 
            'created_at', 'completed_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'completed_at']
    
    def get_progress_percentage(self, obj):
        if obj.total_rows == 0:
            return 0
        return round((obj.processed_rows / obj.total_rows) * 100, 2)

class FileUploadSerializer(serializers.Serializer):
    """Serializer for file uploads (CSV import, receipts)"""
    file = serializers.FileField()
    
    def validate_file(self, value):
        # Add file validation logic here
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError("File size cannot exceed 10MB.")
        return value