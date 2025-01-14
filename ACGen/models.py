from django.db import models


# StandardString Model
class StandardString(models.Model):
    string_id = models.AutoField(primary_key=True)
    string_name = models.CharField(max_length=255)
    string_content = models.TextField()

    def __str__(self):
        return self.string_name

# ClusterTemplate Model
class ClusterTemplate(models.Model):
    cluster_id = models.AutoField(primary_key=True)
    cluster_name = models.CharField(max_length=255)
    cluster_string = models.TextField()
    block_type = models.CharField(max_length=255)
    uploaded_by = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)
    segment = models.CharField(max_length=255)

    def __str__(self):
        return self.cluster_name

# Parameter Model
class Parameter(models.Model):
    parameter_id = models.AutoField(primary_key=True)
    parameter_name = models.CharField(max_length=255)
    section = models.CharField(max_length=255)
    data_type = models.CharField(max_length=255)
    cluster = models.ForeignKey(
        ClusterTemplate, on_delete=models.CASCADE, related_name="parameters"
    )
    assignment_value = models.TextField(null=True, blank=True)
    uploaded_by = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)
    sort_order = models.IntegerField()
    drive_io_assignment_value = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.parameter_name

# ViewParameter Model (for database view)
class ViewParameter(models.Model):
    cluster_name = models.CharField(max_length=255)
    parameter_id = models.IntegerField()
    section = models.CharField(max_length=255)
    parameter_name = models.CharField(max_length=255)
    data_type = models.CharField(max_length=255)
    assignment_value = models.TextField(null=True, blank=True)
    uploaded_by = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField()
    block_type = models.CharField(max_length=255)
    drive_io_assignment_value = models.TextField(null=True, blank=True)
    segment = models.CharField(max_length=255)

    class Meta:
        managed = False  # Indicates it's a view, not a table
        db_table = "viewParameters"