from rest_framework import serializers
from .models import StandardString, ClusterTemplate, Parameter

# StandardString Serializer
class StandardStringSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandardString
        fields = '__all__'

# ClusterTemplate Serializer
class ClusterTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClusterTemplate
        fields = '__all__'

# Parameter Serializer
class ParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parameter
        fields = '__all__'
