# api/views/dashboard_views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from transactions.models import Transaction
from receipts.models import Receipt
from vat_returns.models import VATReturn
from api.serializers.dashboard_serializers import DashboardStatsSerializer, RecentActivitySerializer

class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get dashboard statistics"""
        user = request.user
        
        # Get date ranges
        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        last_month_end = current_month_start - timedelta(days=1)
        
        # Current month stats
        current_transactions = Transaction.objects.filter(
            user=user,
            date__gte=current_month_start,
            date__lte=today
        )
        
        # Last month stats for comparison
        last_month_transactions = Transaction.objects.filter(
            user=user,
            date__gte=last_month_start,
            date__lte=last_month_end
        )
        
        # Revenue (income transactions)
        current_revenue = current_transactions.filter(
            transaction_type='income'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        last_month_revenue = last_month_transactions.filter(
            transaction_type='income'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        # Expenses (expense transactions - convert to positive for display)
        current_expenses = current_transactions.filter(
            transaction_type='expense'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        current_expenses = abs(current_expenses)
        
        last_month_expenses = last_month_transactions.filter(
            transaction_type='expense'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        last_month_expenses = abs(last_month_expenses)
        
        # Transaction labeling stats
        total_transactions = current_transactions.count()
        labeled_transactions = current_transactions.filter(status='labeled').count()
        labeling_percentage = (labeled_transactions / total_transactions * 100) if total_transactions > 0 else 100
        
        # VAT position (get current or most recent VAT return)
        current_quarter = (today.month - 1) // 3 + 1
        vat_return = VATReturn.objects.filter(
            user=user,
            year=today.year
        ).order_by('-created_at').first()
        
        vat_position = Decimal('0.00')
        vat_status = 'neutral'
        if vat_return:
            vat_position = vat_return.net_vat
            vat_status = 'pay' if vat_position > 0 else 'refund' if vat_position < 0 else 'neutral'
        
        # Calculate percentage changes
        revenue_change = self._calculate_percentage_change(current_revenue, last_month_revenue)
        expense_change = self._calculate_percentage_change(current_expenses, last_month_expenses)
        
        stats = {
            'revenue': {
                'amount': float(current_revenue),
                'change': revenue_change,
                'formatted_amount': f'€{current_revenue:,.2f}'
            },
            'expenses': {
                'amount': float(current_expenses),
                'change': expense_change,
                'formatted_amount': f'€{current_expenses:,.2f}'
            },
            'vat_position': {
                'amount': float(abs(vat_position)),
                'status': vat_status,
                'formatted_amount': f'€{abs(vat_position):,.2f}' + (' to pay' if vat_status == 'pay' else ' refund' if vat_status == 'refund' else '')
            },
            'transaction_labeling': {
                'percentage': round(labeling_percentage, 1),
                'labeled_count': labeled_transactions,
                'total_count': total_transactions,
                'formatted': f'{labeled_transactions}/{total_transactions} complete'
            }
        }
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def recent_activity(self, request):
        """Get recent activity (transactions and receipts)"""
        user = request.user
        limit = int(request.query_params.get('limit', 10))
        
        activities = []
        
        # Recent transactions (labeled ones)
        recent_transactions = Transaction.objects.filter(
            user=user,
            status='labeled'
        ).order_by('-updated_at')[:limit//2]
        
        for transaction in recent_transactions:
            activities.append({
                'id': f'transaction_{transaction.id}',
                'type': 'transaction',
                'title': 'Transaction labeled',
                'description': f'{transaction.description} - €{abs(transaction.amount):,.2f}',
                'time': transaction.updated_at,
                'formatted_time': self._format_activity_time(transaction.updated_at)
            })
        
        # Recent receipts
        recent_receipts = Receipt.objects.filter(
            user=user
        ).order_by('-uploaded_at')[:limit//2]
        
        for receipt in recent_receipts:
            activities.append({
                'id': f'receipt_{receipt.id}',
                'type': 'receipt',
                'title': 'Receipt uploaded',
                'description': receipt.supplier or receipt.file_name,
                'time': receipt.uploaded_at,
                'formatted_time': self._format_activity_time(receipt.uploaded_at)
            })
        
        # Sort by time and limit
        activities.sort(key=lambda x: x['time'], reverse=True)
        activities = activities[:limit]
        
        return Response(activities)
    
    @action(detail=False, methods=['get'])
    def todo_items(self, request):
        """Get todo items for the dashboard"""
        user = request.user
        
        # Count unlinked receipts
        unlinked_receipts = Receipt.objects.filter(
            user=user,
            transaction__isnull=True
        ).count()
        
        # Count unlabeled transactions
        unlabeled_transactions = Transaction.objects.filter(
            user=user,
            status='unlabeled'
        ).count()
        
        # Count overdue VAT returns
        overdue_returns = VATReturn.objects.filter(
            user=user,
            status='draft',
            due_date__lt=timezone.now().date()
        ).count()
        
        todo_items = []
        
        if unlinked_receipts > 0:
            todo_items.append({
                'id': 'link_receipts',
                'title': 'Link receipts',
                'description': f'{unlinked_receipts} receipts to link to transactions',
                'count': unlinked_receipts,
                'action': 'Link now',
                'action_color': 'blue'
            })
        
        if unlabeled_transactions > 0:
            todo_items.append({
                'id': 'label_transactions',
                'title': 'Label transactions',
                'description': f'{unlabeled_transactions} transactions need categorizing',
                'count': unlabeled_transactions,
                'action': 'Label now',
                'action_color': 'orange'
            })
        
        if overdue_returns > 0:
            todo_items.append({
                'id': 'submit_returns',
                'title': 'Submit VAT returns',
                'description': f'{overdue_returns} returns are overdue',
                'count': overdue_returns,
                'action': 'Submit',
                'action_color': 'red'
            })
        
        return Response(todo_items)
    
    @action(detail=False, methods=['get'])
    def current_vat_return(self, request):
        """Get current VAT return status"""
        user = request.user
        
        # Get current quarter/year
        today = timezone.now().date()
        current_quarter = f'Q{(today.month - 1) // 3 + 1}'
        current_year = today.year
        
        # Try to get current period return
        vat_return = VATReturn.objects.filter(
            user=user,
            period=current_quarter,
            year=current_year
        ).first()
        
        if not vat_return:
            # Get most recent return if current doesn't exist
            vat_return = VATReturn.objects.filter(
                user=user
            ).order_by('-year', '-period').first()
        
        if not vat_return:
            return Response({
                'period': f'{current_quarter} {current_year}',
                'status': 'not_started',
                'completion_percentage': 0,
                'status_message': 'Not started'
            })
        
        # Calculate completion percentage based on status and data completeness
        completion_percentage = 0
        status_message = 'Draft'
        
        if vat_return.status == 'draft':
            # Check if has transactions/line items
            if vat_return.line_items.exists():
                completion_percentage = 80
                status_message = 'Ready to review'
            else:
                completion_percentage = 20
                status_message = 'In progress'
        elif vat_return.status == 'submitted':
            completion_percentage = 100
            status_message = 'Submitted'
        elif vat_return.status == 'paid':
            completion_percentage = 100
            status_message = 'Completed'
        
        return Response({
            'id': vat_return.id,
            'period': vat_return.period_display,
            'status': vat_return.status,
            'completion_percentage': completion_percentage,
            'status_message': status_message,
            'due_date': vat_return.due_date,
            'net_vat': float(vat_return.net_vat)
        })
    
    def _calculate_percentage_change(self, current, previous):
        """Calculate percentage change between two values"""
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        
        change = ((current - previous) / previous) * 100
        return round(float(change), 1)
    
    def _format_activity_time(self, timestamp):
        """Format timestamp for activity display"""
        now = timezone.now()
        diff = now - timestamp
        
        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}h ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}m ago"
        else:
            return "Just now"


