# api/serializers/dashboard_serializers.py
from rest_framework import serializers

class DashboardStatsSerializer(serializers.Serializer):
    revenue = serializers.DictField()
    expenses = serializers.DictField()
    vat_position = serializers.DictField()
    transaction_labeling = serializers.DictField()

class RecentActivitySerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    time = serializers.DateTimeField()
    formatted_time = serializers.CharField()