from rest_framework import serializers
from .models import StandardString, ClusterTemplate, Parameter, GenerationLog, ControlLibrary
import re


class ControlLibrarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ControlLibrary
        fields = '__all__'


# StandardString Serializer
class StandardStringSerializer(serializers.ModelSerializer):
    class Meta:
        model = StandardString
        fields = '__all__'

# ClusterTemplate Serializer
class ClusterTemplateSerializer(serializers.ModelSerializer):
    dependencies = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    
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
    


class GenerationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenerationLog
        fields = ['id', 'user', 'generation_time', 'project_name', 'project_file_name']
        read_only_fields = ['id', 'user', 'generation_time']

    def validate_project_file_name(self, value):
        # Match A followed by 4 digits or I followed by 3 digits
        if not re.search(r'\bA\d{4}\b|\bI\d{3}\b', value):
            raise serializers.ValidationError(
                "project_file_name must contain a project code in the format AXXXX (4 digits) or IXXX (3 digits)."
            )
        return value
