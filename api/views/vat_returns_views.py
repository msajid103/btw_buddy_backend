# Update your vat_returns_views.py - complete viewset with fixed available_periods

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q
from datetime import date, datetime
from vat_returns.models import VATReturn, VATReturnLineItem
from api.serializers.vat_returns_serializers import (
    VATReturnSerializer, 
    VATReturnSummarySerializer,
    VATReturnSubmissionSerializer,
    VATReturnLineItemSerializer
)

class VATReturnViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return VATReturnSummarySerializer
        elif self.action == 'submit':
            return VATReturnSubmissionSerializer
        return VATReturnSerializer
    
    def get_queryset(self):
        return VATReturn.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Create or get existing VAT return for the period"""
        period = serializer.validated_data["period"]
        year = serializer.validated_data["year"]

        # Check if VAT return already exists for this period
        existing_return = VATReturn.objects.filter(
            user=self.request.user,
            period=period,
            year=year
        ).first()

        if existing_return:
            # Return existing return instead of creating duplicate
            return existing_return

        # Calculate due date
        due_date = self._calculate_due_date(period, year)
        
        # Create new VAT return
        vat_return = VATReturn.objects.create(
            user=self.request.user,
            period=period,
            year=year,
            due_date=due_date,
            status="draft"
        )

        # Calculate VAT amounts from transactions
        vat_return.calculate_vat_amounts()
        vat_return.save()

        return vat_return

    def list(self, request, *args, **kwargs):
        """List VAT returns with optional filtering by period and year"""
        queryset = self.get_queryset()
        
        # Filter by period and year if provided
        period = request.query_params.get('period')
        year = request.query_params.get('year')
        
        if period:
            queryset = queryset.filter(period=period)
        if year:
            try:
                year_int = int(year)
                queryset = queryset.filter(year=year_int)
            except (ValueError, TypeError):
                pass
        
        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def current_period(self, request):
        """Get the current VAT period return"""
        today = date.today()
        current_period, current_year = self._get_current_vat_period(today)
        
        vat_return, created = VATReturn.objects.get_or_create(
            user=request.user,
            period=current_period,
            year=current_year,
            defaults={
                'due_date': self._calculate_due_date(current_period, current_year),
                'status': 'draft'
            }
        )
        
        if created or vat_return.total_output_vat == 0:
            vat_return.calculate_vat_amounts()
            vat_return.save()
        
        serializer = self.get_serializer(vat_return)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='available_periods')
    def available_periods(self, request):
        """Get available VAT periods for selection"""
        current_year = date.today().year
        periods = []
        
        for year in range(current_year - 2, current_year + 1):
            for quarter in ['Q1', 'Q2', 'Q3', 'Q4']:
                due_date = self._calculate_due_date(quarter, year)
                periods.append({
                    'period': quarter,
                    'year': year,
                    'display': f"{quarter} {year}",
                    'due_date': due_date,
                    'is_current': self._is_current_period(quarter, year)
                })
        
        # Sort by year and quarter (most recent first)
        periods.sort(key=lambda x: (x['year'], x['period']), reverse=True)
        return Response(periods)
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit VAT return"""
        vat_return = self.get_object()
        
        if vat_return.status != 'draft':
            return Response(
                {'error': 'Only draft returns can be submitted'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = VATReturnSubmissionSerializer(data=request.data)
        if serializer.is_valid():
            vat_return.status = 'submitted'
            vat_return.submitted_at = timezone.now()
            vat_return.save()
            
            return Response({
                'message': 'VAT return submitted successfully',
                'submission_date': vat_return.submitted_at,
                'reference': f"VAT-{vat_return.year}-{vat_return.period}"
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def recalculate(self, request, pk=None):
        """Recalculate VAT amounts based on current transactions"""
        vat_return = self.get_object()
        
        if vat_return.status != 'draft':
            return Response(
                {'error': 'Only draft returns can be recalculated'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        vat_return.calculate_vat_amounts()
        vat_return.save()
        
        serializer = self.get_serializer(vat_return)
        return Response({
            'message': 'VAT return recalculated successfully',
            'data': serializer.data
        })
    
    @action(detail=True, methods=['get'], url_path='export_pdf')
    def export_pdf(self, request, pk=None):
        """Export VAT return as PDF"""
        vat_return = self.get_object()
        
        # Here you would implement PDF generation
        # For now, return the data that would be in the PDF
        return Response({
            'message': 'PDF export would be generated here',
            'filename': f"VAT_Return_{vat_return.period}_{vat_return.year}.pdf",
            'data': VATReturnSerializer(vat_return).data
        })
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get VAT return statistics"""
        user_returns = self.get_queryset()
        current_year = date.today().year
        
        stats = {
            'total_returns': user_returns.count(),
            'returns_this_year': user_returns.filter(year=current_year).count(),
            'submitted_returns': user_returns.filter(status='submitted').count(),
            'paid_returns': user_returns.filter(status='paid').count(),
            'draft_returns': user_returns.filter(status='draft').count(),
            'overdue_returns': user_returns.filter(
                status='draft',
                due_date__lt=date.today()
            ).count()
        }
        
        # Calculate average VAT amounts
        completed_returns = user_returns.exclude(status='draft')
        if completed_returns.exists():
            total_output_vat = sum(r.total_output_vat for r in completed_returns)
            total_input_vat = sum(r.total_input_vat for r in completed_returns)
            total_net_vat = sum(r.net_vat for r in completed_returns)
            
            count = completed_returns.count()
            stats.update({
                'average_output_vat': total_output_vat / count,
                'average_input_vat': total_input_vat / count,
                'average_net_vat': total_net_vat / count,
            })
        
        return Response(stats)
    
    def _get_current_vat_period(self, date_obj):
        """Determine current VAT period based on date"""
        month = date_obj.month
        year = date_obj.year
        
        if month <= 3:
            return 'Q1', year
        elif month <= 6:
            return 'Q2', year
        elif month <= 9:
            return 'Q3', year
        else:
            return 'Q4', year
    
    def _is_current_period(self, period, year):
        """Check if the given period is the current VAT period"""
        current_period, current_year = self._get_current_vat_period(date.today())
        return period == current_period and year == current_year
    
    def _calculate_due_date(self, period, year):
        """Calculate due date for VAT return"""
        # VAT returns are typically due one month after the period ends
        period_end_dates = {
            'Q1': date(year, 3, 31),
            'Q2': date(year, 6, 30),
            'Q3': date(year, 9, 30),
            'Q4': date(year, 12, 31),
        }
        
        period_end = period_end_dates[period]
        
        # Add one month for due date
        if period_end.month == 12:
            return date(period_end.year + 1, 1, 31)
        else:
            next_month = period_end.month + 1
            # Handle different month lengths
            try:
                return date(period_end.year, next_month, 31)
            except ValueError:
                # If next month doesn't have 31 days, use the last day
                import calendar
                last_day = calendar.monthrange(period_end.year, next_month)[1]
                return date(period_end.year, next_month, last_day)