from django.contrib import admin
from .models import VATReturn, VATReturnLineItem

admin.site.register(VATReturn)
admin.site.register(VATReturnLineItem)
