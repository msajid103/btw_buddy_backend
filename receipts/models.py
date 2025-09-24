from decimal import Decimal
from django.db import models
from accounts.models import User
from django.utils.timezone import now
from transactions.models import Transaction, Category

class Receipt(models.Model):
    STATUS_CHOICES = [
        ('processed', 'Processed'),
        ('pending', 'Pending'),
        ('error', 'Error'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='receipts')
    transaction = models.ForeignKey(
        Transaction, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='receipts'
    )
    
    # File information
    file = models.FileField(upload_to='receipts/%Y/%m/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, blank=True)  # pdf, jpg, png
    file_size = models.BigIntegerField(default=0)  # in bytes
    
    # Extracted information
    supplier = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    receipt_date = models.DateField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    vat_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('21.00'),
        help_text="VAT rate as percentage (e.g., 21.00 for 21%)"
    )
    
    # Status and processing
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    processing_notes = models.TextField(blank=True)
    confidence_score = models.FloatField(default=0.0)  # OCR confidence
    
    # Metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'receipts'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'uploaded_at']),
        ]

    def __str__(self):
        return f"{self.file_name} - {self.supplier or 'Unknown'}"

    def save(self, *args, **kwargs):
        # Extract file type from filename
        if self.file_name and not self.file_type:
            self.file_type = self.file_name.split('.')[-1].lower()
        
        # Auto-calculate VAT amount if not set
        if self.vat_rate and self.amount:
            # Calculate VAT inclusive amount
            vat_exclusive = self.amount / (1 + (self.vat_rate / 100))
            self.vat_amount = self.amount - vat_exclusive
        
        super().save(*args, **kwargs)

    @property
    def formatted_amount(self):
        return f"€{self.amount:,.2f}"
    
    @property
    def is_linked(self):
        return self.transaction is not None