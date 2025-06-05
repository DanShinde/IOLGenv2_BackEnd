from django.db import models

# Create your models here.
class IOVProject(models.Model):
    name = models.CharField(max_length=100)
    plc_endpoint = models.CharField(max_length=255)

    def __str__(self) -> str:
        return self.name

class Tag(models.Model):
    project = models.ForeignKey(IOVProject, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    type = models.CharField(max_length=10)
    panel_number = models.CharField(max_length=10)
    location = models.CharField(max_length=100)
    order = models.IntegerField()

    def __str__(self) -> str:
        return f"{self.name} ({self.project.name})"

class UserAccess(models.Model):
    email = models.EmailField()
    allowed_projects = models.ManyToManyField(IOVProject)