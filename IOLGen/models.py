from django.db import models


# Define the Segment model
# Kept because it is referenced by other apps (accounts.UserProfile.segments,
# ACGen models, accounts serializers). All other IOLGen models were removed
# when the IO-list tooling moved to the standalone OneDesigner app.
class Segment(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
