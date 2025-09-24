from decimal import Decimal
from rest_framework import serializers
from django.db.models import Sum
from transactions.models import Category

class CategorySerializer(serializers.ModelSerializer):
    transaction_count = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'category_type', 'color', 'is_active', 'transaction_count', 'total_amount', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
    
    def get_transaction_count(self, obj):
        return obj.transactions.count()
    
    def get_total_amount(self, obj):
        total = obj.transactions.aggregate(total=Sum('amount'))['total']
        return total or Decimal('0.00')
