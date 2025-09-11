from rest_framework import generics, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, CharFilter, DateFilter, ChoiceFilter
from django.db.models import Q, Sum, Count
from django.db.models.functions import Extract, TruncMonth
from django.utils.dateparse import parse_date
from django.http import HttpResponse
from decimal import Decimal
import csv
import io
from datetime import datetime, timedelta

from .models import Transaction, Account, Category, Receipt, TransactionImport
from .serializers import (
    TransactionSerializer, TransactionListSerializer, TransactionCreateUpdateSerializer,
    AccountSerializer, CategorySerializer, ReceiptSerializer, TransactionImportSerializer,
    TransactionBulkActionSerializer, TransactionStatsSerializer, FileUploadSerializer
)



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


class TransactionViewSet(viewsets.ModelViewSet):
    """ViewSet for handling transactions CRUD operations"""
    permission_classes = [IsAuthenticated]
    filterset_class = TransactionFilter
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['description', 'account__name', 'category__name']
    ordering_fields = ['date', 'amount', 'status', 'created_at']
    ordering = ['-date', '-created_at']

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).select_related(
            'account', 'category'
        ).prefetch_related('receipts')

    def get_serializer_class(self):
        if self.action == 'list':
            return TransactionListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return TransactionCreateUpdateSerializer
        return TransactionSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get transaction statistics"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Basic stats
        total_transactions = queryset.count()
        income_sum = queryset.filter(amount__gt=0).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        expense_sum = queryset.filter(amount__lt=0).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        net_amount = income_sum + expense_sum
        total_vat = queryset.aggregate(Sum('vat_amount'))['vat_amount__sum'] or Decimal('0')

        # Status breakdown
        status_breakdown = queryset.values('status').annotate(count=Count('id'))
        status_dict = {item['status']: item['count'] for item in status_breakdown}

        # Monthly breakdown (last 12 months)
        monthly_stats = queryset.annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            count=Count('id'),
            income=Sum('amount', filter=Q(amount__gt=0)),
            expenses=Sum('amount', filter=Q(amount__lt=0))
        ).order_by('month')

        stats_data = {
            'total_transactions': total_transactions,
            'total_income': income_sum,
            'total_expenses': abs(expense_sum),
            'net_amount': net_amount,
            'total_vat': total_vat,
            'labeled_count': status_dict.get('labeled', 0),
            'pending_count': status_dict.get('pending', 0),
            'unlabeled_count': status_dict.get('unlabeled', 0),
            'monthly_stats': list(monthly_stats)
        }

        serializer = TransactionStatsSerializer(stats_data)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_action(self, request):
        """Perform bulk actions on multiple transactions"""
        serializer = TransactionBulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        transaction_ids = serializer.validated_data['transaction_ids']
        action = serializer.validated_data['action']

        # Get transactions belonging to current user
        transactions = Transaction.objects.filter(
            id__in=transaction_ids,
            user=request.user
        )

        if transactions.count() != len(transaction_ids):
            return Response(
                {'error': 'Some transactions not found or do not belong to you'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Perform the action
        result = self._perform_bulk_action(transactions, action, serializer.validated_data)
        
        return Response(result)

    def _perform_bulk_action(self, transactions, action, validated_data):
        """Helper method to perform bulk actions"""
        if action == 'delete':
            count = transactions.count()
            transactions.delete()
            return {'message': f'{count} transactions deleted successfully'}

        elif action == 'change_category':
            category_id = validated_data.get('category_id')
            try:
                category = Category.objects.get(id=category_id, user=self.request.user)
                transactions.update(category=category, status='labeled')
                return {'message': f'{transactions.count()} transactions updated successfully'}
            except Category.DoesNotExist:
                return {'error': 'Category not found'}

        elif action == 'change_status':
            new_status = validated_data.get('status')
            transactions.update(status=new_status)
            return {'message': f'{transactions.count()} transactions updated successfully'}

        elif action == 'label':
            # Auto-label based on description patterns or rules
            labeled_count = 0
            for transaction in transactions:
                # Simple auto-labeling logic (can be enhanced)
                if transaction.status == 'unlabeled':
                    transaction.status = 'labeled'
                    transaction.save()
                    labeled_count += 1
            return {'message': f'{labeled_count} transactions labeled successfully'}

    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export transactions to CSV"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Get specific transaction IDs if provided
        transaction_ids = request.query_params.get('ids')
        if transaction_ids:
            ids = [int(id) for id in transaction_ids.split(',')]
            queryset = queryset.filter(id__in=ids)

        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions.csv"'

        writer = csv.writer(response)
        # Use the same headers as your import expects
        writer.writerow([
            'Date', 'Description', 'Amount', 'Type', 'VAT Amount', 'Category', 
            'Account', 'Status', 'Has Receipt', 'Reference', 'Notes'
        ])

        for transaction in queryset:
            writer.writerow([
                transaction.date.strftime('%m/%d/%Y'),  # Match your CSV format
                transaction.description,
                transaction.amount,
                transaction.transaction_type,
                transaction.vat_amount,
                transaction.category.name if transaction.category else '',
                transaction.account.name,
                transaction.status,
                'TRUE' if transaction.has_receipt else 'FALSE',  # Match your CSV format
                transaction.reference_number,
                transaction.notes
            ])

        return response

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def import_csv(self, request):
        """Import transactions from CSV file"""
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        csv_file = serializer.validated_data['file']
        
        # Create import record
        import_record = TransactionImport.objects.create(
            user=request.user,
            filename=csv_file.name,
            status='processing'
        )

        try:
            # Process CSV
            result = self._process_csv_import(csv_file, request.user, import_record)
            return Response({
                'import_id': import_record.id,
                'message': 'Import completed',
                'stats': result
            })
        except Exception as e:
            import_record.status = 'failed'
            import_record.error_log = str(e)
            import_record.save()
            return Response(
                {'error': f'Import failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _process_csv_import(self, csv_file, user, import_record):
        """Process CSV import with flexible field name handling"""
        decoded_file = csv_file.read().decode('utf-8')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        total_rows = 0
        successful_rows = 0
        failed_rows = 0
        errors = []

        # Field mapping to handle different CSV header variations
        FIELD_MAPPING = {
            'date': ['date', 'Date', 'DATE'],
            'description': ['description', 'Description', 'DESCRIPTION'],
            'amount': ['amount', 'Amount', 'AMOUNT'],
            'type': ['type', 'Type', 'TYPE', 'transaction_type'],
            'vat_amount': ['vat_amount', 'VAT Amount', 'vat amount', 'VAT_AMOUNT', 'VAT'],
            'category': ['category', 'Category', 'CATEGORY'],
            'account': ['account', 'Account', 'ACCOUNT'],
            'status': ['status', 'Status', 'STATUS'],
            'has_receipt': ['has_receipt', 'Has Receipt', 'has receipt', 'HAS_RECEIPT'],
            'reference': ['reference', 'Reference', 'REFERENCE', 'reference_number'],
            'notes': ['notes', 'Notes', 'NOTES']
        }

        def get_field_value(row, field_name):
            """Get value from row using field mapping"""
            variations = FIELD_MAPPING.get(field_name, [field_name])
            for variation in variations:
                if variation in row:
                    return row[variation]
            return None

        # Get or create default account
        default_account, _ = Account.objects.get_or_create(
            user=user,
            name='Imported Account',
            defaults={'bank_name': 'CSV Import'}
        )

        for row_num, row in enumerate(reader, 1):
            total_rows += 1
            try:
                # Parse row data using field mapping
                date_str = get_field_value(row, 'date')
                description = get_field_value(row, 'description')
                amount_str = get_field_value(row, 'amount') or '0'
                type_str = get_field_value(row, 'type') or 'expense'
                vat_str = get_field_value(row, 'vat_amount') or '0'
                
                if not date_str or not description:
                    raise ValueError("Missing required fields: date or description")

                # Parse date (handle different formats)
                try:
                    date = datetime.strptime(date_str, '%m/%d/%Y').date()
                except ValueError:
                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        date = parse_date(date_str)
                
                if not date:
                    raise ValueError(f"Invalid date format: {date_str}")

                # Parse amounts
                amount = Decimal(amount_str)
                vat_amount = Decimal(vat_str)
                
                # Handle transaction type
                transaction_type = 'income' if type_str.lower() == 'income' else 'expense'
                
                # Handle account and category by name (create if they don't exist)
                account_name = get_field_value(row, 'account')
                category_name = get_field_value(row, 'category')
                
                # Get or create account
                if account_name:
                    account, _ = Account.objects.get_or_create(
                        user=user,
                        name=account_name,
                        defaults={'bank_name': 'CSV Import'}
                    )
                else:
                    account = default_account
                
                # Get or create category
                category = None
                if category_name:
                    category, _ = Category.objects.get_or_create(
                        user=user,
                        name=category_name,
                        defaults={'category_type': transaction_type}
                    )

                # Handle status
                status_str = get_field_value(row, 'status') or 'unlabeled'
                status = status_str if status_str in dict(Transaction.STATUS_CHOICES) else 'unlabeled'

                # Handle has_receipt
                has_receipt_str = get_field_value(row, 'has_receipt') or 'FALSE'
                has_receipt = has_receipt_str.upper() in ['TRUE', '1', 'YES']

                # Create transaction
                transaction = Transaction.objects.create(
                    user=user,
                    account=account,
                    category=category,
                    date=date,
                    description=description,
                    amount=amount,
                    transaction_type=transaction_type,
                    vat_amount=vat_amount,
                    status=status,
                    has_receipt=has_receipt,
                    reference_number=get_field_value(row, 'reference') or '',
                    notes=get_field_value(row, 'notes') or '',
                    import_reference=f"{import_record.id}-{row_num}"
                )
                
                successful_rows += 1

            except Exception as e:
                failed_rows += 1
                errors.append(f"Row {row_num}: {str(e)}")
                # Log the full row for debugging
                errors.append(f"Row data: {dict(row)}")

        # Update import record
            import_record.total_rows = total_rows
            import_record.processed_rows = total_rows
            import_record.successful_rows = successful_rows
            import_record.failed_rows = failed_rows
            import_record.status = 'completed' if failed_rows == 0 else 'partial'
            import_record.error_log = '\n'.join(errors) if errors else ''
            import_record.completed_at = datetime.now()
            import_record.save()

        return {
            'total_rows': total_rows,
            'successful_rows': successful_rows,
            'failed_rows': failed_rows,
            'errors': errors[:10]  # Return first 10 errors
        }

class AccountViewSet(viewsets.ModelViewSet):
    """ViewSet for managing accounts"""
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Account.objects.filter(user=self.request.user).annotate(
            transaction_count=Count('transactions')
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for managing categories"""
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering = ['name']

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user).annotate(
            transaction_count=Count('transactions'),
            total_amount=Sum('transactions__amount')
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def create_defaults(self, request):
        """Create default categories for new users"""
        default_categories = [
            {'name': 'Office Supplies', 'category_type': 'expense', 'color': '#EF4444'},
            {'name': 'Equipment', 'category_type': 'expense', 'color': '#F97316'},
            {'name': 'Utilities', 'category_type': 'expense', 'color': '#EAB308'},
            {'name': 'Software', 'category_type': 'expense', 'color': '#22C55E'},
            {'name': 'Services', 'category_type': 'income', 'color': '#3B82F6'},
            {'name': 'Consulting', 'category_type': 'income', 'color': '#8B5CF6'},
            {'name': 'Products', 'category_type': 'income', 'color': '#EC4899'},
        ]

        created_categories = []
        for cat_data in default_categories:
            category, created = Category.objects.get_or_create(
                user=request.user,
                name=cat_data['name'],
                defaults=cat_data
            )
            if created:
                created_categories.append(category.name)

        return Response({
            'message': f'Created {len(created_categories)} default categories',
            'categories': created_categories
        })


class ReceiptViewSet(viewsets.ModelViewSet):
    """ViewSet for managing receipts"""
    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return Receipt.objects.filter(transaction__user=self.request.user)

    @action(detail=False, methods=['post'])
    def upload(self, request):
        """Upload receipt for a transaction"""
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

        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data['file']
        receipt = Receipt.objects.create(
            transaction=transaction,
            file=file,
            filename=file.name,
            file_size=file.size,
            content_type=file.content_type
        )

        # Update transaction receipt status
        transaction.has_receipt = True
        transaction.save()

        return Response(
            ReceiptSerializer(receipt, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class TransactionImportViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing import history"""
    serializer_class = TransactionImportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TransactionImport.objects.filter(user=self.request.user)


# Additional utility views
class DashboardStatsView(generics.GenericAPIView):
    """Get dashboard statistics"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Recent transactions
        recent_transactions = Transaction.objects.filter(user=user)[:5]
        
        # Quick stats
        this_month = datetime.now().date().replace(day=1)
        this_month_transactions = Transaction.objects.filter(
            user=user,
            date__gte=this_month
        )
        
        stats = {
            'total_transactions': Transaction.objects.filter(user=user).count(),
            'total_accounts': Account.objects.filter(user=user).count(),
            'total_categories': Category.objects.filter(user=user).count(),
            'unlabeled_count': Transaction.objects.filter(user=user, status='unlabeled').count(),
            'this_month_income': this_month_transactions.filter(amount__gt=0).aggregate(
                Sum('amount')
            )['amount__sum'] or Decimal('0'),
            'this_month_expenses': abs(this_month_transactions.filter(amount__lt=0).aggregate(
                Sum('amount')
            )['amount__sum'] or Decimal('0')),
            'recent_transactions': TransactionListSerializer(
                recent_transactions, 
                many=True, 
                context={'request': request}
            ).data
        }
        
        return Response(stats)