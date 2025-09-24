from rest_framework import serializers
from transactions.models import Account

class AccountSerializer(serializers.ModelSerializer):
    transaction_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Account
        fields = ['id', 'name', 'account_number', 'bank_name', 'is_active', 'transaction_count', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
    
    def get_transaction_count(self, obj):
        return obj.transactions.count()

