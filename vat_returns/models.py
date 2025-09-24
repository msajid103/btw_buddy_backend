from django.db.models import Sum
from decimal import Decimal
from datetime import date
from django.db import models
from accounts.models import User
from django.utils.timezone import now
from transactions.models import Transaction

class VATReturn(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]
    
    PERIOD_CHOICES = [
        ('Q1', 'Q1'),
        ('Q2', 'Q2'),
        ('Q3', 'Q3'),
        ('Q4', 'Q4'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vat_returns')
    period = models.CharField(max_length=2, choices=PERIOD_CHOICES)
    year = models.PositiveIntegerField()
    
    # VAT calculation fields
    output_vat_standard = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    output_vat_reduced = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    output_vat_zero = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    input_vat_standard = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    input_vat_capital = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Sales amounts (excl VAT)
    sales_standard_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sales_reduced_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sales_zero_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sales_exempt = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Purchase amounts (excl VAT)
    purchases_standard_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    purchases_capital = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Adjustments and corrections
    adjustments = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    previous_corrections = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Calculated fields
    total_output_vat = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_input_vat = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    net_vat = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Status and dates
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    due_date = models.DateField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'vat_returns'
        unique_together = ['user', 'period', 'year']
        ordering = ['-year', '-period']

    def __str__(self):
        return f"VAT Return {self.period} {self.year} - {self.user.full_name}"

    @property
    def period_display(self):
        return f"{self.period} {self.year}"
    
    def calculate_vat_amounts(self):
        """Auto-calculate VAT amounts based on transactions"""

        # Define period date ranges
        period_ranges = {
            'Q1': (date(self.year, 1, 1), date(self.year, 3, 31)),
            'Q2': (date(self.year, 4, 1), date(self.year, 6, 30)),
            'Q3': (date(self.year, 7, 1), date(self.year, 9, 30)),
            'Q4': (date(self.year, 10, 1), date(self.year, 12, 31)),
        }

        start_date, end_date = period_ranges[self.period]

        # Get transactions for the period
        transactions = Transaction.objects.filter(
            user=self.user,
            date__range=(start_date, end_date)
        )

        # --- Income transactions (sales) ---
        income_transactions = transactions.filter(transaction_type='income')

        # Standard rate ~21%
        standard_income = income_transactions.filter(
            vat_rate__gte=Decimal("20.5"), vat_rate__lte=Decimal("21.5")
        ).aggregate(total_amount=Sum('amount'), total_vat=Sum('vat_amount'))
        self.sales_standard_rate = standard_income['total_amount'] or Decimal('0.00')
        self.output_vat_standard = standard_income['total_vat'] or Decimal('0.00')

        # Reduced rate ~9%
        reduced_income = income_transactions.filter(
            vat_rate__gte=Decimal("8.5"), vat_rate__lte=Decimal("9.5")
        ).aggregate(total_amount=Sum('amount'), total_vat=Sum('vat_amount'))
        self.sales_reduced_rate = reduced_income['total_amount'] or Decimal('0.00')
        self.output_vat_reduced = reduced_income['total_vat'] or Decimal('0.00')

        # Zero rate
        zero_income = income_transactions.filter(
            vat_rate__lte=Decimal("0.1")
        ).aggregate(total_amount=Sum('amount'), total_vat=Sum('vat_amount'))
        self.sales_zero_rate = zero_income['total_amount'] or Decimal('0.00')
        self.output_vat_zero = zero_income['total_vat'] or Decimal('0.00')

        # --- Expense transactions (purchases) ---
        expense_transactions = transactions.filter(transaction_type='expense')

        # Standard expenses
        standard_expenses = expense_transactions.filter(
            vat_rate__gte=Decimal("20.5"), vat_rate__lte=Decimal("21.5")
        ).aggregate(total_amount=Sum('amount'), total_vat=Sum('vat_amount'))
        self.purchases_standard_rate = abs(standard_expenses['total_amount'] or Decimal('0.00'))
        self.input_vat_standard = abs(standard_expenses['total_vat'] or Decimal('0.00'))

        # Capital expenses (equipment, etc.)
        capital_expenses = expense_transactions.filter(
            category__name__icontains='equipment'
        ).aggregate(total_amount=Sum('amount'), total_vat=Sum('vat_amount'))
        self.purchases_capital = abs(capital_expenses['total_amount'] or Decimal('0.00'))
        self.input_vat_capital = abs(capital_expenses['total_vat'] or Decimal('0.00'))

        # --- Totals ---
        self.total_output_vat = self.output_vat_standard + self.output_vat_reduced + self.output_vat_zero
        self.total_input_vat = self.input_vat_standard + self.input_vat_capital
        self.net_vat = self.total_output_vat - self.total_input_vat + self.adjustments + self.previous_corrections

    def save(self, *args, **kwargs):
        # Auto-calculate if this is a new return or amounts haven't been manually set
        if not self.pk or self.total_output_vat == 0:
            self.calculate_vat_amounts()
        
        super().save(*args, **kwargs)


class VATReturnLineItem(models.Model):
    """Detailed line items for VAT returns"""
    vat_return = models.ForeignKey(VATReturn, on_delete=models.CASCADE, related_name='line_items')
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE)
    
    # Override amounts if needed for corrections
    original_amount = models.DecimalField(max_digits=12, decimal_places=2)
    adjusted_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    original_vat = models.DecimalField(max_digits=12, decimal_places=2)
    adjusted_vat = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'vat_return_line_items'
        unique_together = ['vat_return', 'transaction']
    
    @property
    def effective_amount(self):
        return self.adjusted_amount if self.adjusted_amount is not None else self.original_amount
    
    @property
    def effective_vat(self):
        return self.adjusted_vat if self.adjusted_vat is not None else self.original_vat