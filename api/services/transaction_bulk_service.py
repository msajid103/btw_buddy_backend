from transactions.models import Transaction, Category
from django.core.exceptions import ObjectDoesNotExist

class TransactionBulkService:
    """Encapsulates bulk transaction operations"""

    def __init__(self, user):
        self.user = user

    def perform(self, transaction_ids, action, validated_data):
        transactions = Transaction.objects.filter(
            id__in=transaction_ids, user=self.user
        )

        if transactions.count() != len(transaction_ids):
            return {'error': 'Some transactions not found or do not belong to you'}

        if action == 'delete':
            count = transactions.count()
            transactions.delete()
            return {'message': f'{count} transactions deleted successfully'}

        if action == 'change_category':
            category_id = validated_data.get('category_id')
            try:
                category = Category.objects.get(id=category_id, user=self.user)
                transactions.update(category=category, status='labeled')
                return {'message': f'{transactions.count()} transactions updated successfully'}
            except ObjectDoesNotExist:
                return {'error': 'Category not found'}

        if action == 'change_status':
            new_status = validated_data.get('status')
            transactions.update(status=new_status)
            return {'message': f'{transactions.count()} transactions updated successfully'}

        if action == 'label':
            labeled_count = 0
            for t in transactions:
                if t.status == 'unlabeled':
                    t.status = 'labeled'
                    t.save()
                    labeled_count += 1
            return {'message': f'{labeled_count} transactions labeled successfully'}

        return {'error': 'Invalid action'}
