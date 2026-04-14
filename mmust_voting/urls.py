# mmust_voting/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),  
    path('', include('voting.urls')),
    path('chatbot/', include('chatbot.urls')),
    path('security/', include('security.urls')),
    path('accountability/', include('accountability.urls')),
]

# Error handlers
handler404 = 'voting.views.handler404'
handler500 = 'voting.views.handler500'

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)