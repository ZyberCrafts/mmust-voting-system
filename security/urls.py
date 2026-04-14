from django.urls import path
from . import views

app_name = 'security'

urlpatterns = [
    path('', views.security_dashboard, name='dashboard'),
    path('<int:pk>/', views.attack_detail, name='attack_detail'),
]