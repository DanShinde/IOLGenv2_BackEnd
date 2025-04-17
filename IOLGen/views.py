from io import BytesIO
from django.http import HttpResponse
from django.shortcuts import render
import numpy as np
import requests
import pandas as pd
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets
from rest_framework.response import Response
from .models import Segment, PLC, IODevice, Project, Module, IOList, Signal, ProjectReport
from .serializers import (
    SegmentSerializer, PLCSerializer, IODeviceSerializer, ProjectSerializer,
    ModuleSerializer, IOListSerializer, SignalSerializer, ProjectReportSerializer
)
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required




class SegmentViewSet(viewsets.ReadOnlyModelViewSet):
    # permission_classes = [IsAuthenticated]
    queryset = Segment.objects.all()
    serializer_class = SegmentSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        segment_names = queryset.values_list('name', flat=True)
        return Response(segment_names)

class PLCViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = PLC.objects.all()
    serializer_class = PLCSerializer

class IODeviceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = IODevice.objects.all()
    serializer_class = IODeviceSerializer

class ProjectViewSet(viewsets.ModelViewSet):
    # permission_classes = [IsAuthenticated]  # Require authentication
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    
class ProjectsView(TemplateView):
    template_name = "IOLGen/project_list.html"

@login_required
def get_project_list(request):
    projects = Project.objects.all()
    context = {}
    context['projects'] = projects # type: ignore
    return render(request, 'IOLGen/partials/projectTable.html', {'projects': projects})
    

class IOListViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = IOList.objects.select_related('project').all()
    serializer_class = IOListSerializer
    

class ProjectReportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]  # Require authentication
    queryset = ProjectReport.objects.all()
    serializer_class = ProjectReportSerializer

class ModuleViewSet(viewsets.ModelViewSet):
    # permission_classes = [IsAuthenticated]  # Require authentication
    serializer_class = ModuleSerializer
    queryset = Module.objects.none()  # Default queryset to satisfy DRF

    def get_queryset(self):
        """
        Limit the queryset to modules associated with the user's assigned segments.
        """
        user = self.request.user

        if hasattr(user, "profile"):
            # Get the segments assigned to the user's profile
            user_segments = user.profile.segments.all()
            return Module.objects.filter(segment__in=user_segments)

        # If the user doesn't have a profile, return an empty queryset
        return Module.objects.none()

    def perform_create(self, serializer):
        # Only allow users in 'Managers' or 'SegmentSMEs' group to add
        # if not self.request.user.groups.filter(name__in=['Managers', 'SegmentSMEs']).exists():
        #     raise PermissionDenied("You do not have permission to add this module.")
        serializer.save()

    def perform_destroy(self, instance):
        # Only allow users in 'Managers' or 'SegmentSMEs' group to delete
        if not self.request.user.groups.filter(name__in=['Managers', 'SegmentSMEs']).exists():
            raise PermissionDenied("You do not have permission to delete this module.")
        instance.delete()


class SignalViewSet(viewsets.ModelViewSet):
    # permission_classes = [IsAuthenticated]  # Require authentication
    serializer_class = SignalSerializer
    queryset = Module.objects.none()  # Default queryset to satisfy DRF

    def get_queryset(self):
        """
        This view should return a list of all the signals
        for the module specified by the `module_id` parameter.
        """
        module_id = self.request.query_params.get('module_id', None)
        if module_id is not None:
            return Signal.objects.filter(module_id=module_id).select_related('module')
        return Signal.objects.select_related('module').all()
    
    def perform_create(self, serializer):
        # Only allow users in 'Managers' or 'SegmentSMEs' group to add
        if not self.request.user.groups.filter(name__in=['Managers', 'SegmentSMEs']).exists():
            raise PermissionDenied("You do not have permission to add this signal.")
        serializer.save()

    def perform_destroy(self, instance):
        # Only allow users in 'Managers' or 'SegmentSMEs' group to delete
        if not self.request.user.groups.filter(name__in=['Managers', 'SegmentSMEs']).exists():
            raise PermissionDenied("You do not have permission to delete this signal.")
        instance.delete()




class ExportIOListfromV1(APIView):
    def get(self, request, project_name):
        # Fetch data from the external API
        api_url = f"http://iol.pythonanywhere.com/apiio/{project_name}"
        response = requests.get(api_url)
        
        if response.status_code != 200:
            return HttpResponse("Failed to fetch data", status=500)
        
        data = response.json()
        iolist = data.get("iolist", [])
        
        if not iolist:
            return HttpResponse("No IO list data available", status=204)
        
        # Prepare data for DataFrame
        io_data = []
        for item in iolist:
            io_data.append([
                item.get("id"),
                item.get("name"),
                item.get("code"),
                item.get("tag"),
                item.get("signal_type"),
                item.get("io_address"),
                item.get("device_type"),
                item.get("actual_description"),
                item.get("panel_number"),
                item.get("node"),  # IO Module Name
                item.get("module_position"),
                item.get("channel"),
                None,  # Pin (not available in data)
                item.get("location"),  # Remarks (not available in data)
                None   # DataType (not available in data)
            ])
        
        # Convert to DataFrame
        columns = ["Sr.No", "Equipment Name", "Code", "Tag", "Signal Type", "I/O Address", 
                   "Device Type", "Function Description", "Panel Number", "IO Module Name", 
                   "Module Position", "Channel", "Pin",  "Remarks", "DataType"]
        df = pd.DataFrame(io_data, columns=columns)
        
        # Extract unique panels
        panels = df['Panel Number'].unique()

        # Create an in-memory Excel file
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')

        field_data = pd.DataFrame(columns=columns)
        Sheets = {}
        # Iterate over panels and write each panel's data to a separate sheet
        for panel in panels:

            panel_data = df[(df['Panel Number'] == panel) & (df['Remarks'] == "CP")].reset_index(drop=True)
            
            # Create a sequence for I/O Address (0.0, 0.1, ..., 0.7, 1.0, ..., etc.)
            num_rows = len(panel_data)
            sequence = np.floor(np.arange(num_rows) / 8) + (np.arange(num_rows) % 8) / 10.0
            panel_data.loc[:, 'I/O Address'] = sequence
            
            # Add prefix based on Signal Type ('DI' -> 'I', 'DO' -> 'Q')
            panel_data['I/O Address'] = panel_data.apply(
                lambda row: f"I{row['I/O Address']}" if row['Signal Type'] == 'DI' else f"Q{row['I/O Address']}",
                axis=1
            )
            Sheets[panel] = panel_data

            # Extract numerical part of the 'Panel Number' (e.g., 'CC01' → '1')
            panel_number_numeric = ''.join(filter(str.isdigit, panel)).lstrip('0')
            io_module_name = f"IO{panel_number_numeric}"

            # Assign the generated IO Module Name
            panel_data['IO Module Name'] = io_module_name + '01'

            # Assign Module Position: 1 for first 16, 2 for next 16, and so on
            panel_data["Module Position"] = (panel_data.index // 16) + 1

            # Assign Channel: 1 to 16, then repeat
            panel_data["Channel"] = (panel_data.index % 16) + 1  
            panel_data["Pin"] = "-"
            panel_data["DataType"] = "Bool"
            panel_data["Remarks"] = ""



            # ---- Field Devices ----
            # Filter data for 'FD' (Field Devices)
            current_field_data = df[(df['Panel Number'] == panel) & (df['Remarks'] == "FD")].copy()  # Use .copy()

            if not current_field_data.empty:


                # Generate I/O Address sequence for field devices (1000.0, 1000.1, ..., 1001.7, ...)
                num_rows_field = len(current_field_data)  # Get length after appending
                field_sequence = 1000.0 + np.floor(np.arange(num_rows_field) / 8) + (np.arange(num_rows_field) % 8) / 10.0

                # Assign the sequence
                current_field_data.loc[:, 'I/O Address'] = field_sequence

                # Add prefix ('DI' -> 'I', 'DO' -> 'Q')
                current_field_data['I/O Address'] =current_field_data.apply(
                    lambda row: f"I{row['I/O Address']}" if row['Signal Type'] == 'DI' else f"Q{row['I/O Address']}",
                    axis=1
                )

                # Assign IO Module Name
                # Generate IO Module Names: Start from "02", increment every 16 rows
                module_numbers = (2 + np.arange(num_rows_field) // 16).astype(str).tolist()

                # Assign the generated IO Module Names to 'IO Module Name'
                current_field_data['IO Module Name'] = [f"IO{panel_number_numeric}{num.zfill(2)}" for num in module_numbers]

                # Set Module Position to '-'
                current_field_data['Module Position'] = '-'
                current_field_data['DataType'] = 'Bool'
                current_field_data['Remarks'] = ''
                
                # Assign Channel values (X0, X1, ..., X7, repeating every 2 rows)
                current_field_data['Channel'] = [f"X{(i // 2) % 8}" for i in range(len(current_field_data))]

                # Assign Pin values (alternating between Pin 4 and Pin 2)
                current_field_data['Pin'] = ['Pin 4' if i % 2 == 0 else 'Pin 2' for i in range(len(current_field_data))]
                # Append to the main field_data DataFrame
                field_data = pd.concat([field_data, current_field_data], ignore_index=True)
        for sheet in Sheets:
            Sheets[sheet].to_excel(writer, sheet_name=sheet[:31], index=False)
        field_data.to_excel(writer, sheet_name="PLC01-Field IO", index=False)

        workbook = writer.book
        border_format = workbook.add_format({'bottom': 2})  # Thick bottom border

        for sheet_name, worksheet in writer.sheets.items():
            num_rows = worksheet.dim_rowmax + 1  # Get the actual number of rows in the sheet
            for i in range(17, num_rows, 16):  # Start from row 17 (skipping header), then every 16 rows
                worksheet.set_row(i - 1, None, border_format)  # Adjust for 0-based indexing


        # Save the Excel file to memory
        writer.close()
        output.seek(0)


        update_io_Module(request, Sheets, field_data, f"https://iol.pythonanywhere.com/apiio/update/")
        # Return the file as an HTTP response for download
        response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename={project_name}_IOList.xlsx'
        
        return response


def update_io_Module(request, panel_data_dict, field_data,db_update_url):
    """
    Sends a request to update the database with combined IO data.

    :param panel_data_dict: Dictionary containing panel numbers as keys and DataFrames as values
    :param field_data: DataFrame containing field IO data

    :param db_update_url: API endpoint URL for updating the database
    """
    try:
        # Prepare a unified list for both panel and field data
        io_update_data = []

        # Process panel data
        for panel_number, panel_df in panel_data_dict.items():
            panel_entries = panel_df[['Sr.No', 'IO Module Name']].copy()
            panel_entries.rename(columns={'Sr.No': 'id', 'IO Module Name': 'iomodule_name'}, inplace=True)
            io_update_data.extend(panel_entries.to_dict(orient="records"))

        # Process field data
        field_entries = field_data[['Sr.No', 'IO Module Name']].copy()
        field_entries.rename(columns={'Sr.No': 'id', 'IO Module Name': 'iomodule_name'}, inplace=True)
        io_update_data.extend(field_entries.to_dict(orient="records"))

        # Prepare the payload
        update_payload = {
            "io_data": io_update_data  # Unified data structure
        }

        session = requests.Session()
        session.get("https://iol.pythonanywhere.com")  # Get CSRF cookie first
        csrf_token = session.cookies.get("csrftoken")
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf_token  # Send CSRF token
        }
        # Send the POST request
        response = requests.post(db_update_url, json=update_payload, headers=headers, cookies=session.cookies)

        # Check response
        if response.status_code == 200:
            print("Database updated successfully")
        else:
            print(f"Database update failed: {response.status_code}, {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to database API: {str(e)}")


