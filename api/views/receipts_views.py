from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.http import HttpResponse
import django_filters
from datetime import datetime
from decimal import Decimal

from receipts.models import Receipt
from api.serializers.receipt_serializers import (
    ReceiptSerializer, 
    ReceiptUploadSerializer, 
    ReceiptLinkSerializer,
    ReceiptStatsSerializer
)
from transactions.models import Transaction


class ReceiptFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Receipt.STATUS_CHOICES)
    date_from = django_filters.DateFilter(field_name='receipt_date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='receipt_date', lookup_expr='lte')
    uploaded_from = django_filters.DateFilter(field_name='uploaded_at', lookup_expr='gte')
    uploaded_to = django_filters.DateFilter(field_name='uploaded_at', lookup_expr='lte')
    amount_min = django_filters.NumberFilter(field_name='amount', lookup_expr='gte')
    amount_max = django_filters.NumberFilter(field_name='amount', lookup_expr='lte')
    is_linked = django_filters.BooleanFilter(method='filter_linked')
    category = django_filters.NumberFilter(field_name='category')
    
    class Meta:
        model = Receipt
        fields = ['status', 'file_type', 'supplier', 'category']
    
    def filter_linked(self, queryset, name, value):
        if value is True:
            return queryset.filter(transaction__isnull=False)
        elif value is False:
            return queryset.filter(transaction__isnull=True)
        return queryset


class ReceiptViewSet(viewsets.ModelViewSet):
    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ReceiptFilter
    search_fields = ['file_name', 'supplier', 'processing_notes']
    ordering_fields = ['uploaded_at', 'amount', 'receipt_date', 'status']
    ordering = ['-uploaded_at']

    def get_queryset(self):
        return Receipt.objects.filter(user=self.request.user).select_related(
            'transaction', 'category'
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def upload(self, request):
        """Handle file upload and create receipt"""
        serializer = ReceiptUploadSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if serializer.is_valid():
            file = serializer.validated_data['file']
            
            # Create receipt instance
            receipt_data = {
                'user': request.user,
                'file': file,
                'file_name': file.name,
                'file_size': file.size,
                'supplier': serializer.validated_data.get('supplier', ''),
                'amount': serializer.validated_data.get('amount', Decimal('0.00')),
                'receipt_date': serializer.validated_data.get('receipt_date'),
                'vat_rate': serializer.validated_data.get('vat_rate', Decimal('21.00')),
            }
            
            # Link to category if provided
            category_id = serializer.validated_data.get('category')
            if category_id:
                from transactions.models import Category
                receipt_data['category'] = Category.objects.get(id=category_id)
            
            # Link to transaction if provided
            transaction_id = serializer.validated_data.get('transaction')
            if transaction_id:
                transaction = Transaction.objects.get(id=transaction_id)
                receipt_data['transaction'] = transaction
                receipt_data['status'] = 'processed'
                # Update transaction to show it has receipt
                transaction.has_receipt = True
                transaction.save()
            
            receipt = Receipt.objects.create(**receipt_data)
            
            # TODO: Trigger OCR processing here if needed
            # self.process_receipt_ocr(receipt)
            
            response_serializer = ReceiptSerializer(
                receipt, 
                context={'request': request}
            )
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def bulk_link(self, request):
        """Link multiple receipts to a single transaction"""
        serializer = ReceiptLinkSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            receipt_ids = serializer.validated_data['receipt_ids']
            transaction_id = serializer.validated_data['transaction_id']
            
            transaction = Transaction.objects.get(id=transaction_id)
            receipts = Receipt.objects.filter(
                id__in=receipt_ids,
                user=request.user
            )
            
            # Update receipts
            updated_count = receipts.update(
                transaction=transaction,
                status='processed',
                processed_at=timezone.now()
            )
            
            # Update transaction
            transaction.has_receipt = True
            transaction.save()
            
            return Response({
                'message': f'{updated_count} receipts linked successfully',
                'updated_count': updated_count
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def link_transaction(self, request, pk=None):
        """Link a single receipt to a transaction"""
        receipt = self.get_object()
        transaction_id = request.data.get('transaction_id')
        
        if not transaction_id:
            return Response(
                {'error': 'transaction_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            transaction = Transaction.objects.get(
                id=transaction_id,
                user=request.user
            )
        except Transaction.DoesNotExist:
            return Response(
                {'error': 'Transaction not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        receipt.transaction = transaction
        receipt.status = 'processed'
        receipt.processed_at = timezone.now()
        receipt.save()
        
        # Update transaction
        transaction.has_receipt = True
        transaction.save()
        
        serializer = ReceiptSerializer(receipt, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def unlink_transaction(self, request, pk=None):
        """Unlink receipt from transaction"""
        receipt = self.get_object()
        
        if receipt.transaction:
            transaction = receipt.transaction
            receipt.transaction = None
            receipt.status = 'pending'
            receipt.processed_at = None
            receipt.save()
            
            # Check if transaction still has other receipts
            has_other_receipts = transaction.receipts.exclude(id=receipt.id).exists()
            transaction.has_receipt = has_other_receipts
            transaction.save()
        
        serializer = ReceiptSerializer(receipt, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get receipt statistics"""
        queryset = self.get_queryset()
        
        stats = queryset.aggregate(
            total_receipts=Count('id'),
            total_amount=Sum('amount'),
            processed_receipts=Count('id', filter=Q(status='processed')),
            pending_receipts=Count('id', filter=Q(status='pending')),
            error_receipts=Count('id', filter=Q(status='error')),
            linked_receipts=Count('id', filter=Q(transaction__isnull=False)),
            unlinked_receipts=Count('id', filter=Q(transaction__isnull=True))
        )
        
        # Handle null values
        for key, value in stats.items():
            if value is None:
                stats[key] = 0
        
        if stats['total_amount'] is None:
            stats['total_amount'] = Decimal('0.00')
        
        serializer = ReceiptStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def recent_uploads(self, request):
        """Get recent uploads"""
        recent = self.get_queryset()[:5]
        serializer = ReceiptSerializer(
            recent, 
            many=True, 
            context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download receipt file"""
        receipt = self.get_object()
        
        if not receipt.file:
            return Response(
                {'error': 'File not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create response with file
        response = HttpResponse(
            receipt.file.read(),
            content_type='application/octet-stream'
        )
        response['Content-Disposition'] = f'attachment; filename="{receipt.file_name}"'
        return response

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        """Bulk delete receipts"""
        receipt_ids = request.data.get('receipt_ids', [])
        
        if not receipt_ids:
            return Response(
                {'error': 'receipt_ids is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        receipts = self.get_queryset().filter(id__in=receipt_ids)
        
        # Update linked transactions
        for receipt in receipts:
            if receipt.transaction:
                transaction = receipt.transaction
                # Check if transaction will have other receipts after deletion
                has_other_receipts = transaction.receipts.exclude(id=receipt.id).exists()
                transaction.has_receipt = has_other_receipts
                transaction.save()
        
        deleted_count = receipts.count()
        receipts.delete()
        
        return Response({
            'message': f'{deleted_count} receipts deleted successfully',
            'deleted_count': deleted_count
        })

    def process_receipt_ocr(self, receipt):
        """
        Placeholder for OCR processing
        This would integrate with OCR service to extract:
        - Supplier name
        - Amount
        - Date
        - VAT information
        """
        # TODO: Implement OCR processing
        # This could use services like:
        # - Google Cloud Vision API
        # - Amazon Textract
        # - Azure Form Recognizer
        # - Open source solutions like Tesseract
        pass