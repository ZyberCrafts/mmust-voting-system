# routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/live/(?P<election_id>\w+)/$', consumers.PublicLiveTrackingConsumer.as_asgi()),
    re_path(r'ws/admin/live/(?P<election_id>\w+)/$', consumers.AdminLiveTrackingConsumer.as_asgi()),
]