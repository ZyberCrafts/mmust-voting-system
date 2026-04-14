from django.contrib import admin
from .models import ManifestoItem, RatingSession, LeaderRating, NotificationLog

class ManifestoItemAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'description', 'order')
    list_filter = ('candidate__election',)
    search_fields = ('description',)

class RatingSessionAdmin(admin.ModelAdmin):
    list_display = ('election', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active',)

class LeaderRatingAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'rating', 'created_at')
    list_filter = ('session', 'rating')
    search_fields = ('user__username',)

admin.site.register(ManifestoItem, ManifestoItemAdmin)
admin.site.register(RatingSession, RatingSessionAdmin)
admin.site.register(LeaderRating, LeaderRatingAdmin)
admin.site.register(NotificationLog)