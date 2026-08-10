from rest_framework import serializers

from .models import Item, Assignment, Dispatch, History, Reservation


class ItemSerializer(serializers.ModelSerializer):
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)
    current_location_display = serializers.CharField(read_only=True)

    class Meta:
        model = Item
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def validate_serial_number(self, value):
        qs = Item.objects.filter(serial_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('An item with this serial number already exists.')
        return value


class AssignmentSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_serial_number = serializers.CharField(source='item.serial_number', read_only=True)
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    is_active = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)

    class Meta:
        model = Assignment
        fields = '__all__'

    def get_is_active(self, obj):
        return obj.is_active()


class DispatchSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_serial_number = serializers.CharField(source='item.serial_number', read_only=True)
    item_type = serializers.CharField(source='item.item_type', read_only=True)
    is_active = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)

    class Meta:
        model = Dispatch
        fields = '__all__'

    def get_is_active(self, obj):
        return obj.is_active()


class HistorySerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_serial_number = serializers.CharField(source='item.serial_number', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model = History
        fields = '__all__'


class ReservationSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    reserved_for_username = serializers.CharField(source='reserved_for.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Reservation
        fields = '__all__'
        read_only_fields = ['reserved_by', 'status', 'fulfilled_assignment', 'created_at']

    def validate(self, attrs):
        item = attrs.get('item') or getattr(self.instance, 'item', None)
        start_date = attrs.get('start_date') or getattr(self.instance, 'start_date', None)
        end_date = attrs.get('end_date') or getattr(self.instance, 'end_date', None)

        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({'end_date': 'End date cannot be before start date.'})

        if item and start_date and end_date:
            conflicts = Reservation.objects.filter(item=item, status='PENDING')
            if self.instance:
                conflicts = conflicts.exclude(pk=self.instance.pk)
            for existing in conflicts:
                if existing.overlaps(start_date, end_date):
                    who = existing.reserved_for.get_full_name() or existing.reserved_for.username
                    raise serializers.ValidationError(
                        f'{item.name} is already reserved for {who} from {existing.start_date} to {existing.end_date}.'
                    )
        return attrs
