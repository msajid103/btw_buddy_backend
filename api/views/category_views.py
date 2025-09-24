from api.serializers.category_serializer import CategorySerializer
from transactions.models import Category
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated


class CategoryViewSet(ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
