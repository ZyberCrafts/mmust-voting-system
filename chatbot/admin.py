from django.contrib import admin
from .models import ChatSession, ChatMessage

class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('message', 'is_bot', 'intent', 'feedback', 'timestamp')
    can_delete = False

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'user', 'created_at', 'last_activity')
    list_filter = ('created_at',)
    search_fields = ('session_id', 'user__username')
    inlines = [ChatMessageInline]
    actions = ['delete_expired']

    def delete_expired(self, request, queryset):
        # mark expired? but we have a management command for cleanup
        self.message_user(request, "Use management command 'cleanup_chat_sessions' for bulk cleanup.")
    delete_expired.short_description = "Delete expired sessions (use management command)"

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'message_preview', 'is_bot', 'intent', 'feedback', 'timestamp')
    list_filter = ('is_bot', 'intent', 'feedback', 'timestamp')
    search_fields = ('message',)
    readonly_fields = ('timestamp',)

    def message_preview(self, obj):
        return obj.message[:50] + ('...' if len(obj.message) > 50 else '')
    message_preview.short_description = 'Message'