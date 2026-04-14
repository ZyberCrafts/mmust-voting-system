from django.urls import path
from . import views

urlpatterns = [
    path('questionnaire/<int:session_id>/', views.questionnaire, name='questionnaire'),
    path('leader-dashboard/', views.leader_dashboard, name='leader_dashboard'),
]