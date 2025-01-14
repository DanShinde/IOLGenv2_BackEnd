from django.contrib import admin
from .models import ClusterTemplate, Parameter, StandardString, ViewParameter
# Register your models here.
admin.site.register(ClusterTemplate)
admin.site.register(Parameter)
admin.site.register(StandardString)
admin.site.register(ViewParameter)