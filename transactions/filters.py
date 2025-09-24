from datetime import datetime, timedelta
from decimal import Decimal
from django_filters import CharFilter, ChoiceFilter, DateFilter, FilterSet
from django.db.models import Q
from .models import Transaction


class TransactionFilter(FilterSet):
    """Custom filter for transactions"""
    search = CharFilter(method='filter_search')
    date_from = DateFilter(field_name='date', lookup_expr='gte')
    date_to = DateFilter(field_name='date', lookup_expr='lte')
    date_range = CharFilter(method='filter_date_range')
    status = ChoiceFilter(choices=Transaction.STATUS_CHOICES)
    transaction_type = ChoiceFilter(choices=Transaction.TRANSACTION_TYPE_CHOICES)
    account = CharFilter(field_name='account__id')
    category = CharFilter(field_name='category__id')
    has_receipt = CharFilter(method='filter_has_receipt')
    amount_min = CharFilter(method='filter_amount_min')
    amount_max = CharFilter(method='filter_amount_max')

    class Meta:
        model = Transaction
        fields = []

    def filter_search(self, queryset, name, value):
        """Search in description, account name, and category name"""
        return queryset.filter(
            Q(description__icontains=value) |
            Q(account__name__icontains=value) |
            Q(category__name__icontains=value)
        )

    def filter_date_range(self, queryset, name, value):
        """Filter by predefined date ranges"""
        today = datetime.now().date()
        
        if value == 'last7':
            date_from = today - timedelta(days=7)
        elif value == 'last30':
            date_from = today - timedelta(days=30)
        elif value == 'last90':
            date_from = today - timedelta(days=90)
        elif value == 'this_month':
            date_from = today.replace(day=1)
        elif value == 'last_month':
            first_day_this_month = today.replace(day=1)
            date_from = (first_day_this_month - timedelta(days=1)).replace(day=1)
            date_to = first_day_this_month - timedelta(days=1)
            return queryset.filter(date__gte=date_from, date__lte=date_to)
        else:
            return queryset

        return queryset.filter(date__gte=date_from)

    def filter_has_receipt(self, queryset, name, value):
        """Filter by receipt status"""
        has_receipt = value.lower() in ['true', '1', 'yes']
        return queryset.filter(has_receipt=has_receipt)

    def filter_amount_min(self, queryset, name, value):
        """Filter by minimum absolute amount"""
        try:
            amount = Decimal(value)
            return queryset.filter(
                Q(amount__gte=amount) | Q(amount__lte=-amount)
            )
        except:
            return queryset

    def filter_amount_max(self, queryset, name, value):
        """Filter by maximum absolute amount"""
        try:
            amount = Decimal(value)
            return queryset.filter(
                Q(amount__lte=amount, amount__gte=0) | 
                Q(amount__gte=-amount, amount__lt=0)
            )
        except:
            return queryset
