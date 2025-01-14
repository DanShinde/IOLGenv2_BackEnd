from django.contrib import admin
from .models import ClusterTemplate, Parameter, StandardString
# Register your models here.
admin.site.register(ClusterTemplate)
admin.site.register(Parameter)
admin.site.register(StandardString)