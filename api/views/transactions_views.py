import csv
from datetime import datetime
from decimal import Decimal
import io
from humanfriendly import parse_date
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from api.services.transaction_bulk_service import TransactionBulkService
from transactions.filters import TransactionFilter
from transactions.models import Account, Category, Transaction, TransactionImport
from api.serializers.transactions_serializers import FileUploadSerializer, TransactionBulkActionSerializer, TransactionSerializer

class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TransactionFilter

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    

    @action(detail=False, methods=['post'])
    def bulk_action(self, request):
        serializer = TransactionBulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = TransactionBulkService(user=request.user)
        result = service.perform(
            serializer.validated_data['transaction_ids'],
            serializer.validated_data['action'],
            serializer.validated_data,
        )

        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
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
