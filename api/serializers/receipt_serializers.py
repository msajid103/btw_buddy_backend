from rest_framework import serializers
from receipts.models import Receipt
from transactions.models import Transaction


class ReceiptSerializer(serializers.ModelSerializer):
    transaction_id = serializers.CharField(source='transaction.id', read_only=True)
    transaction_description = serializers.CharField(source='transaction.description', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    formatted_amount = serializers.SerializerMethodField()
    is_linked = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Receipt
        fields = [
            'id', 'file_name', 'file_type', 'file_size', 'file_url',
            'supplier', 'amount', 'formatted_amount', 'receipt_date',
            'category', 'category_name', 'vat_amount', 'vat_rate',
            'status', 'processing_notes', 'confidence_score',
            'transaction', 'transaction_id', 'transaction_description',
            'is_linked', 'uploaded_at', 'processed_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'uploaded_at', 'updated_at', 'file_size', 'file_type']
    
    def get_formatted_amount(self, obj):
        return f"€{obj.amount:,.2f}"
    
    def get_is_linked(self, obj):
        return obj.transaction is not None
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None
    
    def validate_transaction(self, value):
        """Ensure transaction belongs to the current user"""
        if value:
            request = self.context.get('request')
            if request and hasattr(request, 'user'):
                if value.user != request.user:
                    raise serializers.ValidationError("Transaction does not belong to the current user.")
        return value
    
    def validate_category(self, value):
        """Ensure category belongs to the current user"""
        if value:
            request = self.context.get('request')
            if request and hasattr(request, 'user'):
                if value.user != request.user:
                    raise serializers.ValidationError("Category does not belong to the current user.")
        return value


class ReceiptUploadSerializer(serializers.Serializer):
    """Serializer for handling file uploads"""
    file = serializers.FileField(required=True)
    supplier = serializers.CharField(max_length=200, required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    receipt_date = serializers.DateField(required=False)
    category = serializers.IntegerField(required=False)
    transaction = serializers.IntegerField(required=False)
    vat_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    
    def validate_file(self, value):
        """Validate file type and size"""
        # Check file size (max 10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File size cannot exceed 10MB.")
        
        # Check file type
        allowed_types = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png']
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Only PDF, JPG, and PNG files are allowed.")
        
        return value
    
    def validate_category(self, value):
        """Validate category exists and belongs to user"""
        if value:
            from transactions.models import Category
            try:
                category = Category.objects.get(id=value)
                request = self.context.get('request')
                if request and hasattr(request, 'user'):
                    if category.user != request.user:
                        raise serializers.ValidationError("Category does not belong to the current user.")
            except Category.DoesNotExist:
                raise serializers.ValidationError("Category does not exist.")
        return value
    
    def validate_transaction(self, value):
        """Validate transaction exists and belongs to user"""
        if value:
            try:
                transaction = Transaction.objects.get(id=value)
                request = self.context.get('request')
                if request and hasattr(request, 'user'):
                    if transaction.user != request.user:
                        raise serializers.ValidationError("Transaction does not belong to the current user.")
            except Transaction.DoesNotExist:
                raise serializers.ValidationError("Transaction does not exist.")
        return value


class ReceiptLinkSerializer(serializers.Serializer):
    """Serializer for linking receipts to transactions"""
    receipt_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=100
    )
    transaction_id = serializers.IntegerField()
    
    def validate_transaction_id(self, value):
        """Validate transaction exists and belongs to user"""
        try:
            transaction = Transaction.objects.get(id=value)
            request = self.context.get('request')
            if request and hasattr(request, 'user'):
                if transaction.user != request.user:
                    raise serializers.ValidationError("Transaction does not belong to the current user.")
        except Transaction.DoesNotExist:
            raise serializers.ValidationError("Transaction does not exist.")
        return value
    
    def validate_receipt_ids(self, value):
        """Validate all receipts exist and belong to user"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            receipts = Receipt.objects.filter(id__in=value, user=request.user)
            if receipts.count() != len(value):
                raise serializers.ValidationError("Some receipts do not exist or don't belong to the current user.")
        return value


class ReceiptStatsSerializer(serializers.Serializer):
    """Serializer for receipt statistics"""
    total_receipts = serializers.IntegerField()
    processed_receipts = serializers.IntegerField()
    pending_receipts = serializers.IntegerField()
    error_receipts = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    linked_receipts = serializers.IntegerField()
    unlinked_receipts = serializers.IntegerField()