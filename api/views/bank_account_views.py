from api.serializers.bank_account_serializers import AccountSerializer
from transactions.models import Account
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated


class AccountViewSet(ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Account.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
