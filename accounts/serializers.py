from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Info
from IOLGen.models import Segment


# Serializers define the API representation.
class InfoSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Info
        fields = ['id','key', 'value']


class RegisterSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(write_only=True)
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name']

    def validate(self, data):
        if data['password']!= data['password2']:
            raise serializers.ValidationError("Password must match")
        return data
    
    def create(self, validated_data):
        user = User.objects.create_user(
            username= validated_data['username'],
            email= validated_data['email'],
            password= validated_data['password'],
            first_name = validated_data['first_name'],
            last_name = validated_data['last_name']
        )
        return user
    

class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Segment
        fields = ["name"]  # Include only the name field or others as needed

# Serializer for UserProfile
class UserProfileSerializer(serializers.ModelSerializer):
    segments = serializers.SerializerMethodField()  # Use the nested serializer for segments
    allowed_clusters = serializers.SerializerMethodField()  # Custom field for allowed clusters

    class Meta:
        model = UserProfile  # Correct model to serialize
        fields = [
            "usertype",
            "segments",
            "is_ac_approved",
            "is_ac_cluster_create_allowed",
            "is_ac_cluster_edit_allowed",
            "is_ac_cluster_delete_allowed",
            "allowed_clusters",
            "created_at",
            "updated_at",
        ]  # Explicitly list fields to include

    def get_segments(self, obj):
        # Return a flat list of segment names
        return list(obj.segments.values_list("name", flat=True))
    
    def get_allowed_clusters(self, obj):
        # Return a flat list of allowed cluster names (or IDs, if needed)
        return list(obj.allowed_clusters.values_list("cluster_name", flat=True))  
