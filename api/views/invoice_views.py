# api/views/invoice_views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum, Q, Count
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
import io
from decimal import Decimal
from datetime import date, datetime, timedelta

from invoices.models import Invoice, InvoiceLine, Customer, InvoiceEmailLog
from api.serializers.invoice_serializers import (
    InvoiceSerializer, 
    InvoiceSummarySerializer,
    InvoiceEmailSerializer,
    InvoiceStatusUpdateSerializer,
    CustomerSerializer,
    NextInvoiceNumberSerializer
)

class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Customer.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class InvoiceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return InvoiceSummarySerializer
        elif self.action == 'send_email':
            return InvoiceEmailSerializer
        elif self.action in ['update_status', 'mark_paid']:
            return InvoiceStatusUpdateSerializer
        return InvoiceSerializer
    
    def get_queryset(self):
        queryset = Invoice.objects.filter(user=self.request.user)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(invoice_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(invoice_date__lte=date_to)
        
        # Search by invoice number or customer name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search) |
                Q(customer__name__icontains=search)
            )
        
        # Update overdue invoices
        self.update_overdue_invoices(queryset)
        
        return queryset.select_related('customer').prefetch_related('lines')
    
    def perform_create(self, serializer):
        # Auto-generate invoice number if not provided
        if not serializer.validated_data.get('invoice_number'):
            serializer.validated_data['invoice_number'] = self.generate_invoice_number()
        
        serializer.save(user=self.request.user)
    
    def update_overdue_invoices(self, queryset=None):
        """Update invoice status to overdue where applicable"""
        if queryset is None:
            queryset = self.get_queryset()
        
        today = timezone.now().date()
        overdue_invoices = queryset.filter(
            status='sent',
            due_date__lt=today
        )
        overdue_invoices.update(status='overdue')
    
    @action(detail=False, methods=['get'])
    def next_number(self, request):
        """Get the next available invoice number"""
        next_number = self.generate_invoice_number()
        serializer = NextInvoiceNumberSerializer({'next_number': next_number})
        return Response(serializer.data)
    
    def generate_invoice_number(self):
        """Generate next invoice number for user"""
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # Find the last invoice for this user in current year/month
        last_invoice = Invoice.objects.filter(
            user=self.request.user,
            invoice_date__year=current_year,
            invoice_date__month=current_month
        ).order_by('-invoice_number').first()
        
        if last_invoice and last_invoice.invoice_number:
            try:
                # Extract number from format INV-YYYY-MM-XXX
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
    
    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        """Generate and download PDF for invoice"""
        invoice = self.get_object()
        
        try:
            # For now, return a simple response
            # In production, you'd use libraries like reportlab or weasyprint
            pdf_content = self.generate_invoice_pdf(invoice)
            
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="invoice-{invoice.invoice_number}.pdf"'
            return response
            
        except Exception as e:
            return Response(
                {'error': f'Failed to generate PDF: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def generate_invoice_pdf(self, invoice):
        """Generate PDF content for invoice"""
        # This is a placeholder - implement with reportlab or weasyprint
        # For now, return a simple text representation
        content = f"""
        INVOICE {invoice.invoice_number}
        
        Date: {invoice.invoice_date}
        Due Date: {invoice.due_date}
        
        Bill To:
        {invoice.customer.name}
        {invoice.customer.address}
        VAT: {invoice.customer.vat_number}
        
        Items:
        """
        
        for line in invoice.lines.all():
            content += f"\n{line.description} - {line.quantity} x €{line.unit_price} = €{line.line_total}"
        
        content += f"""
        
        Subtotal: €{invoice.subtotal}
        VAT: €{invoice.total_vat}
        Total: €{invoice.total}
        
        Payment Instructions:
        {invoice.payment_instructions}
        """
        
        return content.encode('utf-8')
    
    @action(detail=True, methods=['post'])
    def send_email(self, request, pk=None):
        """Send invoice via email"""
        invoice = self.get_object()
        serializer = InvoiceEmailSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Send email
                success = self.send_invoice_email(
                    invoice,
                    serializer.validated_data['to_email'],
                    serializer.validated_data['subject'],
                    serializer.validated_data['message']
                )
                
                if success:
                    # Update invoice status to sent
                    if invoice.status == 'draft':
                        invoice.status = 'sent'
                        invoice.sent_at = timezone.now()
                        invoice.save()
                    
                    return Response({
                        'message': 'Invoice sent successfully',
                        'sent_at': timezone.now()
                    })
                else:
                    return Response(
                        {'error': 'Failed to send invoice email'}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                    
            except Exception as e:
                return Response(
                    {'error': f'Email sending failed: {str(e)}'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def send_invoice_email(self, invoice, to_email, subject, message):
        """Send invoice email with PDF attachment"""
        try:
            # Log the email attempt
            email_log = InvoiceEmailLog.objects.create(
                invoice=invoice,
                to_email=to_email,
                subject=subject,
                message=message
            )
            
            # Generate PDF attachment (placeholder)
            pdf_content = self.generate_invoice_pdf(invoice)
            
            # Send email (configure your email backend in Django settings)
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
                fail_silently=False,
                # In production, add PDF as attachment:
                # attachments=[('invoice.pdf', pdf_content, 'application/pdf')]
            )
            
            # Mark as successful
            email_log.sent_successfully = True
            email_log.save()
            
            return True
            
        except Exception as e:
            # Log the error
            email_log.sent_successfully = False
            email_log.error_message = str(e)
            email_log.save()
            return False
    
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update invoice status"""
        invoice = self.get_object()
        serializer = InvoiceStatusUpdateSerializer(
            data=request.data, 
            context={'instance': invoice}
        )
        
        if serializer.is_valid():
            new_status = serializer.validated_data['status']
            old_status = invoice.status
            
            # Update status
            invoice.status = new_status
            
            # Set timestamp based on status
            if new_status == 'sent' and old_status == 'draft':
                invoice.sent_at = timezone.now()
            elif new_status == 'paid':
                invoice.paid_at = timezone.now()
            
            invoice.save()
            
            return Response({
                'message': f'Invoice status updated from {old_status} to {new_status}',
                'status': new_status
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark invoice as paid"""
        invoice = self.get_object()
        
        if invoice.status == 'paid':
            return Response(
                {'message': 'Invoice is already marked as paid'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invoice.status = 'paid'
        invoice.paid_at = timezone.now()
        invoice.save()
        
        return Response({
            'message': 'Invoice marked as paid',
            'paid_at': invoice.paid_at
        })
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get invoice statistics for dashboard"""
        queryset = self.get_queryset()
        current_month = timezone.now().replace(day=1)
        last_month = (current_month - timedelta(days=1)).replace(day=1)
        
        # Basic counts
        total_invoices = queryset.count()
        draft_count = queryset.filter(status='draft').count()
        sent_count = queryset.filter(status='sent').count()
        paid_count = queryset.filter(status='paid').count()
        overdue_count = queryset.filter(status='overdue').count()
        
        # Financial totals
        total_amount = queryset.aggregate(total=Sum('total'))['total'] or Decimal('0')
        paid_amount = queryset.filter(status='paid').aggregate(total=Sum('total'))['total'] or Decimal('0')
        outstanding_amount = total_amount - paid_amount
        
        # Monthly comparisons
        this_month_total = queryset.filter(
            invoice_date__gte=current_month
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        
        last_month_total = queryset.filter(
            invoice_date__gte=last_month,
            invoice_date__lt=current_month
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        
        # Calculate percentage change
        monthly_change = 0
        if last_month_total > 0:
            monthly_change = float((this_month_total - last_month_total) / last_month_total * 100)
        
        return Response({
            'total_invoices': total_invoices,
            'draft_count': draft_count,
            'sent_count': sent_count,
            'paid_count': paid_count,
            'overdue_count': overdue_count,
            'total_amount': float(total_amount),
            'paid_amount': float(paid_amount),
            'outstanding_amount': float(outstanding_amount),
            'this_month_total': float(this_month_total),
            'last_month_total': float(last_month_total),
            'monthly_change_percentage': monthly_change
        })
    
    @action(detail=False, methods=['get'])
    def dashboard_summary(self, request):
        """Get summary data for dashboard"""
        queryset = self.get_queryset()
        
        # Recent invoices
        recent_invoices = queryset.order_by('-created_at')[:5]
        recent_serializer = InvoiceSummarySerializer(recent_invoices, many=True)
        
        # Overdue invoices
        overdue_invoices = queryset.filter(status='overdue').order_by('due_date')[:5]
        overdue_serializer = InvoiceSummarySerializer(overdue_invoices, many=True)
        
        # This month's revenue
        current_month = timezone.now().replace(day=1)
        this_month_revenue = queryset.filter(
            invoice_date__gte=current_month,
            status='paid'
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        
        return Response({
            'recent_invoices': recent_serializer.data,
            'overdue_invoices': overdue_serializer.data,
            'this_month_revenue': float(this_month_revenue),
            'total_outstanding': float(
                queryset.filter(status__in=['sent', 'overdue']).aggregate(
                    total=Sum('total')
                )['total'] or Decimal('0')
            )
        })
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export invoices to CSV"""
        import csv
        from django.http import HttpResponse
        
        queryset = self.get_queryset()
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="invoices.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Invoice Number', 'Date', 'Customer', 'Status',
            'Subtotal', 'VAT', 'Total', 'Due Date'
        ])
        
        for invoice in queryset:
            writer.writerow([
                invoice.invoice_number,
                invoice.invoice_date.strftime('%Y-%m-%d'),
                invoice.customer.name,
                invoice.status,
                float(invoice.subtotal),
                float(invoice.total_vat),
                float(invoice.total),
                invoice.due_date.strftime('%Y-%m-%d')
            ])
        
        return response
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Create a duplicate of the invoice with new number and date"""
        original_invoice = self.get_object()
        
        # Create duplicate
        duplicate_invoice = Invoice.objects.create(
            user=original_invoice.user,
            customer=original_invoice.customer,
            invoice_number=self.generate_invoice_number(),
            invoice_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            company_name=original_invoice.company_name,
            company_address=original_invoice.company_address,
            company_vat_number=original_invoice.company_vat_number,
            company_chamber_of_commerce=original_invoice.company_chamber_of_commerce,
            notes=original_invoice.notes,
            payment_instructions=original_invoice.payment_instructions,
            status='draft'
        )
        
        # Copy line items
        for line in original_invoice.lines.all():
            InvoiceLine.objects.create(
                invoice=duplicate_invoice,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                vat_rate=line.vat_rate
            )
        
        # Return the duplicate
        serializer = self.get_serializer(duplicate_invoice)
        return Response({
            'message': 'Invoice duplicated successfully',
            'invoice': serializer.data
        }, status=status.HTTP_201_CREATED)