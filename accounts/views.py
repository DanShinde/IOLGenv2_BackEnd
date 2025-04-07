from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions, status, viewsets
from django.contrib.auth.models import User
from .serializers import RegisterSerializer, UserProfileSerializer, InfoSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from .models import UserProfile, Info
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404, redirect
from django.core.cache import cache
from .forms import CustomUserForm
from django.contrib.auth.views import LoginView

# ViewSets define the view behavior.
class InfoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Info.objects.all()
    serializer_class = InfoSerializer

    def get_queryset(self):
        """
        Override to require `key` parameter and return only matching results.
        Uses cache to store and retrieve data.
        """
        key = self.request.query_params.get('key', None)
        info_id = get_object_or_404(Info,key=key).id
        if not key:
            return self.queryset  # No key provided, return all

        # Try to fetch from cache
        cache_key = f"info_{info_id}"
        cached_data = cache.get(cache_key)

        if cached_data:
            print("Cache HIT")  # Debugging cache behavior
            return Info.objects.filter(pk__in=[obj.pk for obj in cached_data])  

        # Query the database if cache miss
        queryset = self.queryset.filter(key=key)

        if not queryset.exists():
            raise ValidationError({"error": f"No value found for key '{key}'"})

        # Store result in cache for future requests (timeout=300 sec)
        cache.set(cache_key, list(queryset), timeout=3600)  # Cache expires in 5 minutes

        print("Cache MISS")  # Debugging cache behavior
        return queryset

    @action(detail=False, methods=['get'])
    def get_by_key(self, request):
        """
        Custom endpoint: /info/get_by_key/?key=some_key
        """
        key = request.query_params.get('key', None)
        if not key:
            return Response({'error': 'Key parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        info_id = get_object_or_404(Info,key=key).id
        cache_key = f"info_{info_id}"
        info = cache.get(cache_key)

        if not info:
            info = get_object_or_404(Info, key=key)
            cache.set(cache_key, info, timeout=300)

        serializer = self.get_serializer(info)
        return Response(serializer.data)



class RegisterViewA(APIView):
    def post(self, request):
        data = request.data
        serializer = RegisterSerializer(data = data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User created successfully",
                "status": True,
                "data": serializer.data
            }, status= status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class LoginViewA(APIView):
    def post(self, request):
        data = request.data
        username = data.get('username')
        password = data.get('password')
        user = User.objects.filter(username= username).first()
        if user and  user.check_password(password):
            refresh = RefreshToken.for_user(user)
            return Response({
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh)
            })
        return Response({"message": "Invalid Credentials"}, status=status.HTTP_400_BAD_REQUEST)

class LogoutViewA(APIView):
     permission_classes = [IsAuthenticated]
     def post(self, request):
          
          try:
               refresh_token = request.data["refresh_token"]
               token = RefreshToken(refresh_token)
               token.blacklist()
               return Response(status=status.HTTP_205_RESET_CONTENT)
          except Exception as e:
               return Response(status=status.HTTP_400_BAD_REQUEST)
          
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):

        user = request.user
        userProfile = UserProfile.objects.get(user=user)
        serializer = UserProfileSerializer(userProfile)
        return Response(serializer.data)
    
class LoginViewW(LoginView):
    redirect_authenticated_user = True
    template_name='accounts/login.html'


def registerw(request):
    form = CustomUserForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect('loginw')
    return render(request, 'accounts/login.html',  {'form': form, 'is_register': True})