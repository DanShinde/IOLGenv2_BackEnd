from rest_framework import serializers
from .models import Segment, PLC, IODevice, Project, Module, IOList, Signal, ProjectReport

class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Segment
        fields = '__all__'

class PLCSerializer(serializers.ModelSerializer):
    class Meta:
        model = PLC
        fields = '__all__'

class IODeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = IODevice
        fields = '__all__'

class ProjectSerializer(serializers.ModelSerializer):
    segments = SegmentSerializer(many=True, read_only=True)
    PLC = PLCSerializer(read_only=True)

    class Meta:
        model = Project
        fields = '__all__'

class ProjectReportSerializer(serializers.ModelSerializer):
    project = ProjectSerializer(read_only=True)

    class Meta:
        model = ProjectReport
        fields = '__all__'

class ModuleSerializer(serializers.ModelSerializer):
    segment = SegmentSerializer(read_only=True)

    class Meta:
        model = Module
        # fields = '__all__'
        fields = ['id', 'module', 'description', 'segment', 'created_by', 'created_at',  'updated_at']

class IOListSerializer(serializers.ModelSerializer):
    project = ProjectSerializer(read_only=True)

    class Meta:
        model = IOList
        fields = '__all__'

class SignalSerializer(serializers.ModelSerializer):
    # segment = SegmentSerializer(read_only=True)
    # module = ModuleSerializer(read_only=True)

    class Meta:
        model = Signal
        fields = '__all__'
        read_only_fields = ['module', 'segment','created_by', 'created_at', 'updated_at', 'updated_by']
        # exclude = ['module', 'segment', 'created_by', 'created_at', 'updated_at', 'updated_by']

