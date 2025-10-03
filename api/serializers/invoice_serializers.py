# api/serializers/invoice_serializers.py

from rest_framework import serializers
from invoices.models import Invoice, InvoiceLine, Customer, InvoiceEmailLog
from decimal import Decimal

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'address', 'vat_number', 'chamber_of_commerce',
            'email', 'phone', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']    


class InvoiceLineSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    vat_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InvoiceLine
        fields = [
            'id', 'description', 'quantity', 'unit_price', 'vat_rate',
            'line_total', 'vat_amount', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'line_total', 'vat_amount', 'created_at', 'updated_at']

    def validate_vat_rate(self, value):
        """Validate VAT rate is one of the allowed Dutch rates"""
        allowed_rates = [Decimal('0.00'), Decimal('9.00'), Decimal('21.00')]
        if value not in allowed_rates:
            raise serializers.ValidationError(
                "VAT rate must be 0%, 9%, or 21% according to Dutch tax law."
            )
        return value

    def validate_quantity(self, value):
        """Ensure quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_unit_price(self, value):
        """Ensure unit price is not negative"""
        if value < 0:
            raise serializers.ValidationError("Unit price cannot be negative.")
        return value


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True)
    customer = CustomerSerializer(read_only=True)
    customer_id = serializers.IntegerField(write_only=True)
    
    # Calculated fields
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_vat = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    vat_breakdown = serializers.JSONField(read_only=True)
    
    # Status helpers
    is_overdue = serializers.BooleanField(read_only=True)
    days_until_due = serializers.SerializerMethodField()
    formatted_total = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'invoice_date', 'due_date',
            'customer', 'customer_id', 'lines',
            'subtotal', 'total_vat', 'total', 'vat_breakdown',
            'notes', 'payment_instructions', 'status',
            'company_logo', 'company_name', 'company_address',
            'company_vat_number', 'company_chamber_of_commerce',
            'sent_at', 'paid_at', 'is_overdue', 'days_until_due',
            'formatted_total', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'subtotal', 'total_vat', 'total', 'vat_breakdown',
            'is_overdue', 'sent_at', 'paid_at', 'created_at', 'updated_at'
        ]

    def get_days_until_due(self, obj):
        """Calculate days until due date"""
        from django.utils import timezone
        if obj.status in ['paid', 'cancelled']:
            return 0
        
        today = timezone.now().date()
        if obj.due_date < today:
            return -(today - obj.due_date).days  # Negative for overdue
        return (obj.due_date - today).days

    def get_formatted_total(self, obj):
        """Format total amount for display"""
        return f"€{obj.total:,.2f}"

    def validate_customer_id(self, value):
        """Ensure customer belongs to the current user"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            try:
                customer = Customer.objects.get(id=value, user=request.user)
                return value
            except Customer.DoesNotExist:
                raise serializers.ValidationError("Customer does not exist or does not belong to you.")
        return value

    def validate_invoice_number(self, value):
        """Ensure invoice number is unique for the user"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            existing = Invoice.objects.filter(
                user=request.user,
                invoice_number=value
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise serializers.ValidationError("Invoice number already exists.")
        return value

    def validate_due_date(self, value):
        """Ensure due date is not in the past"""
        from django.utils import timezone
        if value < timezone.now().date():
            raise serializers.ValidationError("Due date cannot be in the past.")
        return value

    def validate_lines(self, value):
        """Ensure at least one line item exists"""
        if not value:
            raise serializers.ValidationError("Invoice must have at least one line item.")
        return value

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        request = self.context.get('request')
        
        # Set user from request
        validated_data['user'] = request.user
        
        # Get customer
        customer_id = validated_data.pop('customer_id')
        validated_data['customer'] = Customer.objects.get(id=customer_id, user=request.user)
        
        # Create invoice
        invoice = Invoice.objects.create(**validated_data)
        
        # Create line items
        for line_data in lines_data:
            InvoiceLine.objects.create(invoice=invoice, **line_data)
        
        # Recalculate totals
        invoice.calculate_totals()
        invoice.save(update_fields=['subtotal', 'total_vat', 'total', 'vat_breakdown'])
        return invoice

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', [])
        customer_id = validated_data.pop('customer_id', None)
        
        # Update customer if provided
        if customer_id:
            validated_data['customer'] = Customer.objects.get(
                id=customer_id, 
                user=instance.user
            )
        
        # Update invoice fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update line items
        if lines_data:
            # Delete existing lines
            instance.lines.all().delete()
            
            # Create new lines
            for line_data in lines_data:
                InvoiceLine.objects.create(invoice=instance, **line_data)
        
        # Recalculate totals
        instance.calculate_totals()
        return instance


class InvoiceSummarySerializer(serializers.ModelSerializer):
    """Lighter serializer for list views"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    days_until_due = serializers.SerializerMethodField()
    formatted_total = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'invoice_date', 'due_date',
            'customer_name', 'total', 'formatted_total', 'status',
            'is_overdue', 'days_until_due', 'created_at'
        ]

    def get_days_until_due(self, obj):
        """Calculate days until due date"""
        from django.utils import timezone
        if obj.status in ['paid', 'cancelled']:
            return 0
        
        today = timezone.now().date()
        if obj.due_date < today:
            return -(today - obj.due_date).days  # Negative for overdue
        return (obj.due_date - today).days

    def get_formatted_total(self, obj):
        """Format total amount for display"""
        return f"€{obj.total:,.2f}"


class InvoiceEmailSerializer(serializers.Serializer):
    """Serializer for sending invoice emails"""
    to_email = serializers.EmailField()
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField()
    
    def validate_to_email(self, value):
        """Basic email validation"""
        if not value:
            raise serializers.ValidationError("Email address is required.")
        return value


class InvoiceStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating invoice status"""
    status = serializers.ChoiceField(choices=Invoice.STATUS_CHOICES)

    def validate_status(self, value):
        """Validate status transitions"""
        instance = self.context.get('instance')
        if instance:
            # Define allowed transitions
            allowed_transitions = {
                'draft': ['sent', 'cancelled'],
                'sent': ['paid', 'overdue', 'cancelled'],
                'overdue': ['paid', 'cancelled'],
                'paid': ['cancelled'],  # Only allow cancellation of paid invoices
                'cancelled': []  # No transitions from cancelled
            }
            
            current_status = instance.status
            if value not in allowed_transitions.get(current_status, []):
                raise serializers.ValidationError(
                    f"Cannot change status from '{current_status}' to '{value}'"
                )
        
        return value


class NextInvoiceNumberSerializer(serializers.Serializer):
    """Serializer for getting next invoice number"""
    next_number = serializers.CharField(read_only=True)