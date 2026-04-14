from django.urls import path
from . import views

urlpatterns = [
    path('', views.chatbot_ui, name='chatbot_ui'),
    path('api/', views.chatbot_api, name='chatbot_api'),
    path('embed/', views.chatbot_embed, name='chatbot_embed'),
]