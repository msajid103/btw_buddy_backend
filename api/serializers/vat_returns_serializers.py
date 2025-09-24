from rest_framework import serializers
from vat_returns.models import VATReturn, VATReturnLineItem

class VATReturnLineItemSerializer(serializers.ModelSerializer):
    effective_amount = serializers.ReadOnlyField()
    effective_vat = serializers.ReadOnlyField()
    transaction_description = serializers.CharField(source='transaction.description', read_only=True)
    transaction_date = serializers.DateField(source='transaction.date', read_only=True)
    
    class Meta:
        model = VATReturnLineItem
        fields = [
            'id', 'transaction', 'original_amount', 'adjusted_amount',
            'original_vat', 'adjusted_vat', 'notes', 'effective_amount',
            'effective_vat', 'transaction_description', 'transaction_date'
        ]


class VATReturnSerializer(serializers.ModelSerializer):
    line_items = VATReturnLineItemSerializer(many=True, read_only=True)
    period_display = serializers.ReadOnlyField()

    output_vat_change = serializers.SerializerMethodField()
    input_vat_change = serializers.SerializerMethodField()
    net_vat_change = serializers.SerializerMethodField()

    class Meta:
        model = VATReturn
        fields = [
            'id', 'period', 'year', 'period_display',
            'output_vat_standard', 'output_vat_reduced', 'output_vat_zero',
            'input_vat_standard', 'input_vat_capital',
            'sales_standard_rate', 'sales_reduced_rate', 'sales_zero_rate', 'sales_exempt',
            'purchases_standard_rate', 'purchases_capital',
            'adjustments', 'previous_corrections',
            'total_output_vat', 'total_input_vat', 'net_vat',
            'status', 'due_date', 'submitted_at', 'paid_at',
            'created_at', 'updated_at', 'line_items',
            'output_vat_change', 'input_vat_change', 'net_vat_change'
        ]
        read_only_fields = [
            'user', 'total_output_vat', 'total_input_vat', 'net_vat',
            'due_date'  
        ]

    
    def get_output_vat_change(self, obj):
        return self._get_percentage_change(obj, 'total_output_vat')
    
    def get_input_vat_change(self, obj):
        return self._get_percentage_change(obj, 'total_input_vat')
    
    def get_net_vat_change(self, obj):
        return self._get_percentage_change(obj, 'net_vat')
    
    def _get_percentage_change(self, obj, field_name):
        """Calculate percentage change from previous period"""
        try:
            # Get previous period
            previous_period = self._get_previous_period(obj.period, obj.year)
            if not previous_period:
                return None
            
            previous_return = VATReturn.objects.filter(
                user=obj.user,
                period=previous_period['period'],
                year=previous_period['year']
            ).first()
            
            if not previous_return:
                return None
            
            current_value = getattr(obj, field_name)
            previous_value = getattr(previous_return, field_name)
            
            if previous_value == 0:
                return 100 if current_value > 0 else 0
            
            change = ((current_value - previous_value) / previous_value) * 100
            return round(float(change), 2)
        
        except Exception:
            return None
    
    def _get_previous_period(self, period, year):
        """Get previous period and year"""
        period_order = ['Q1', 'Q2', 'Q3', 'Q4']
        current_index = period_order.index(period)
        
        if current_index == 0:
            return {'period': 'Q4', 'year': year - 1}
        else:
            return {'period': period_order[current_index - 1], 'year': year}


class VATReturnSummarySerializer(serializers.ModelSerializer):
    """Lighter serializer for list views"""
    period_display = serializers.ReadOnlyField()
    days_until_due = serializers.SerializerMethodField()
    
    class Meta:
        model = VATReturn
        fields = [
            'id', 'period', 'year', 'period_display', 'status',
            'total_output_vat', 'total_input_vat', 'net_vat',
            'due_date', 'submitted_at', 'paid_at', 'days_until_due'
        ]
    
    def get_days_until_due(self, obj):
        from django.utils import timezone
        if obj.status in ['submitted', 'paid']:
            return 0
        
        today = timezone.now().date()
        if obj.due_date < today:
            return -(today - obj.due_date).days  # Negative for overdue
        return (obj.due_date - today).days


class VATReturnSubmissionSerializer(serializers.Serializer):
    """Serializer for VAT return submission"""
    confirmation = serializers.BooleanField(required=True)
    submission_notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    
    def validate_confirmation(self, value):
        if not value:
            raise serializers.ValidationError("You must confirm the submission.")
        return value