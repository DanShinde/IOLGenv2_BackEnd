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
        read_only_fields = ['uploaded_by', 'uploaded_at', 'updated_by', 'updated_at']

# Parameter Serializer
class ParameterSerializer(serializers.ModelSerializer):
    block_type = serializers.CharField(source="cluster.block_type", read_only=True)

    class Meta:
        model = Parameter
        fields = '__all__'
        read_only_fields = ['uploaded_by', 'uploaded_at', 'updated_by', 'updated_at', 'block_type',]

    def create(self, validated_data):
        request = self.context['request']
        validated_data['uploaded_by'] = request.user.get_full_name()
        validated_data['updated_by'] = request.user.get_full_name()
        print(validated_data)
        # print(validated_data['uploaded_by'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context['request']
        validated_data['updated_by'] = request.user.get_full_name()
        return super().update(instance, validated_data)