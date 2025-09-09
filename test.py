from ACGen.models import ClusterTemplate    
# Get the source and target instances
target_name = "InterfaceTrackedToUntracked"
source_name = "1"+target_name
# source_instance = ClusterTemplate.objects.get(id=2587)  # or any filter
# target_instance = ClusterTemplate.objects.get(id=162)  # or any filter
source_instance = ClusterTemplate.objects.get(cluster_name=source_name)
target_instance = ClusterTemplate.objects.get(cluster_name=target_name)
# Copy specific fields
target_instance.cluster_string = source_instance.cluster_string
target_instance.cluster_path = source_instance.cluster_path
target_instance.block_type = source_instance.block_type
target_instance.dependencies.set(source_instance.dependencies.all())
target_instance.control_library = source_instance.control_library
# Save the target instance
target_instance.save()
# source_instance.delete()  # Optional: delete the source instance if no longer needed
# exec(open('test.py').read())