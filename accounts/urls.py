"""
URL configuration for IOLGenv2_BackEnd project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RegisterViewA, LoginViewA,ProfileView, LogoutViewA, InfoViewSet, registerw
from rest_framework_simplejwt.views import TokenRefreshView
from django.contrib.auth.views import LoginView, LogoutView


# Create a router and register the InfoViewSet
router = DefaultRouter()
router.register(r'info', InfoViewSet, basename='info')


urlpatterns = [
    path('register/', RegisterViewA.as_view()),
    path('login/', LoginViewA.as_view()),
    path('profile/', ProfileView.as_view()),
    path('logout/', LogoutViewA.as_view(), name ='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),  
    path('', include(router.urls)),
    path('loginw/', LoginView.as_view(template_name='accounts/login.html'), name='loginw'),
    path('logoutw/', LogoutView.as_view(next_page='loginw'), name='logoutw'),
    path('registerw/', registerw, name='registerw'),
    # path('registerw/', RegisterView.as_view(template_name='accounts/register.html'), name='registerw'),
]

