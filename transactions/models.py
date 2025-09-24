from decimal import Decimal
from django.db import models
from accounts.models import User
from django.utils.timezone import now

class Account(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=100)  # e.g., "ING Business"
    account_number = models.CharField(max_length=50, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts'
        unique_together = ['user', 'name']

    def __str__(self):
        return f"{self.name} - {self.user.full_name}"


class Category(models.Model):
    CATEGORY_TYPE_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
        ('both', 'Both'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPE_CHOICES, default='both')
    color = models.CharField(max_length=7, default='#6B7280')  # Hex color
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        unique_together = ['user', 'name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return f"{self.name} ({self.category_type})"


class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]

    STATUS_CHOICES = [
        ('labeled', 'Labeled'),
        ('pending', 'Pending'),
        ('unlabeled', 'Unlabeled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    
    date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2,default=Decimal('0.00'),
        help_text="VAT rate as percentage (e.g., 21.00 for 21%)"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unlabeled')
    
    # Receipt/Document fields
    has_receipt = models.BooleanField(default=False)
    receipt_file = models.FileField(upload_to='receipts/', blank=True, null=True)
    
    # Additional metadata
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    
    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Import tracking
    import_reference = models.CharField(max_length=100, blank=True, help_text="Reference for imported transactions")

    class Meta:
        db_table = 'transactions'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'transaction_type']),
        ]

    def __str__(self):
        return f"{self.date} - {self.description} - {self.amount}"

    def save(self, *args, **kwargs):
        # Auto-calculate VAT amount if not explicitly set
        if self.vat_rate is not None and self.amount is not None:
            self.vat_amount = self.amount * (self.vat_rate / Decimal('100'))
            
        # Auto-determine transaction type based on amount
        if self.amount < 0:
            self.transaction_type = 'expense'
        else:
            self.transaction_type = 'income'
        
        
        # Update has_receipt based on receipt_file
        self.has_receipt = bool(self.receipt_file)
        
        super().save(*args, **kwargs)

class TransactionImport(models.Model):
    """Track CSV/bank imports"""
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transaction_imports')
    filename = models.CharField(max_length=255)
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    successful_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='processing')
    error_log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'transaction_imports'
        ordering = ['-created_at']

    def __str__(self):
        return f"Import {self.filename} - {self.status}"
