# invoices/models.py

from decimal import Decimal
from django.db import models
from accounts.models import User
from django.utils.timezone import now
from django.core.validators import MinValueValidator, MaxValueValidator

class Customer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customers')
    name = models.CharField(max_length=200)
    address = models.TextField()
    vat_number = models.CharField(max_length=50, blank=True)
    chamber_of_commerce = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customers'
        ordering = ['name']
        unique_together = ['user', 'name']

    def __str__(self):
        return f"{self.name} - {self.user.full_name}"


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    
    # Invoice identification
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    due_date = models.DateField()
    
    # Company details (for PDF generation)
    company_logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    company_name = models.CharField(max_length=200, blank=True)
    company_address = models.TextField(blank=True)
    company_vat_number = models.CharField(max_length=50, blank=True)
    company_chamber_of_commerce = models.CharField(max_length=50, blank=True)
    
    # Financial totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_vat = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # VAT breakdown (stored as JSON)
    vat_breakdown = models.JSONField(default=dict, help_text="VAT amounts by rate")
    
    # Additional information
    notes = models.TextField(blank=True)
    payment_instructions = models.TextField(blank=True, default='Payment within 30 days of invoice date.')
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sent_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoices'
        ordering = ['-invoice_date', '-created_at']
        unique_together = ['user', 'invoice_number']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'invoice_date']),
            models.Index(fields=['due_date']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer.name}"

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.status in ['paid', 'cancelled']:
            return False
        from django.utils import timezone
        return self.due_date < timezone.now().date()

    def calculate_totals(self):
        """Recalculate invoice totals from line items"""
        lines = self.lines.all()
        
        self.subtotal = Decimal('0.00')
        self.total_vat = Decimal('0.00')
        vat_breakdown = {'0': {'amount': 0, 'vat': 0}, '9': {'amount': 0, 'vat': 0}, '21': {'amount': 0, 'vat': 0}}
        
        for line in lines:
            line_total = line.quantity * line.unit_price
            line_vat = line_total * (line.vat_rate / Decimal('100'))
            
            self.subtotal += line_total
            self.total_vat += line_vat
            
            # Update VAT breakdown
            rate_key = str(int(line.vat_rate))
            if rate_key in vat_breakdown:
                vat_breakdown[rate_key]['amount'] += float(line_total)
                vat_breakdown[rate_key]['vat'] += float(line_vat)
        
        self.total = self.subtotal + self.total_vat
        self.vat_breakdown = vat_breakdown
        
        # Round according to Dutch VAT rules
        self.subtotal = round(self.subtotal, 2)
        self.total_vat = round(self.total_vat, 2)
        self.total = round(self.total, 2)

    def save(self, *args, **kwargs):
        # Auto-generate invoice number if not provided
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        
        # Update status based on dates
        if self.status == 'sent' and self.is_overdue:
            self.status = 'overdue'
        
        # Set company details from user profile if not set
        if not self.company_name and hasattr(self.user, 'profile'):
            profile = self.user.profile
            self.company_name = profile.company_name or f"{self.user.first_name} {self.user.last_name}"
            self.company_address = profile.company_address or ''
            self.company_vat_number = profile.vat_number or ''
            self.company_chamber_of_commerce = profile.chamber_of_commerce or ''
        
        super().save(*args, **kwargs)
        
        # Recalculate totals after saving
        if self.pk:
            self.calculate_totals()
            # Prevent infinite recursion by updating without calling save()
            Invoice.objects.filter(pk=self.pk).update(
                subtotal=self.subtotal,
                total_vat=self.total_vat,
                total=self.total,
                vat_breakdown=self.vat_breakdown
            )

    def generate_invoice_number(self):
        """Generate next invoice number for user"""
        from datetime import datetime
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # Find the last invoice for this user in current year/month
        last_invoice = Invoice.objects.filter(
            user=self.user,
            invoice_date__year=current_year,
            invoice_date__month=current_month
        ).order_by('-invoice_number').first()
        
        if last_invoice and last_invoice.invoice_number:
            # Extract number from format INV-YYYY-MM-XXX
            try:
                parts = last_invoice.invoice_number.split('-')
                if len(parts) >= 4:
                    last_num = int(parts[-1])
                    next_num = last_num + 1
                else:
                    next_num = 1
            except (ValueError, IndexError):
                next_num = 1
        else:
            next_num = 1
        
        return f"INV-{current_year}-{current_month:02d}-{next_num:03d}"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    vat_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="VAT rate as percentage (e.g., 21.00 for 21%)"
    )
    
    # Calculated fields
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoice_lines'
        ordering = ['id']

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.description[:50]}"

    def save(self, *args, **kwargs):
        # Calculate line totals
        self.line_total = self.quantity * self.unit_price
        self.vat_amount = self.line_total * (self.vat_rate / Decimal('100'))
        
        super().save(*args, **kwargs)
        
        # Update invoice totals
        if self.invoice_id:
            self.invoice.calculate_totals()


class InvoiceEmailLog(models.Model):
    """Track invoice email sends"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='email_logs')
    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    sent_successfully = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'invoice_email_logs'
        ordering = ['-sent_at']

    def __str__(self):
        return f"Email for {self.invoice.invoice_number} to {self.to_email}"