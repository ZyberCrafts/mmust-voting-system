from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class ChatSession(models.Model):
    session_id = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)  # optional: link to logged-in user
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Session {self.session_id[:8]} - {self.created_at}"

    def is_expired(self, timeout_minutes=30):
        """Check if session has been inactive for more than timeout minutes."""
        return (timezone.now() - self.last_activity).total_seconds() > timeout_minutes * 60

    def cleanup_old_sessions():
        """Delete sessions older than 7 days."""
        cutoff = timezone.now() - timezone.timedelta(days=7)
        ChatSession.objects.filter(last_activity__lt=cutoff).delete()


class ChatMessage(models.Model):
    INTENT_CHOICES = (
        ('greeting', 'Greeting'),
        ('election', 'Election Info'),
        ('candidate', 'Candidate Info'),
        ('vote', 'Voting Process'),
        ('result', 'Election Results'),
        ('turnout', 'Live Turnout'),
        ('help', 'Help'),
        ('other', 'Other'),
    )
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    message = models.TextField()
    is_bot = models.BooleanField(default=False)
    intent = models.CharField(max_length=20, choices=INTENT_CHOICES, blank=True, help_text="Detected intent of the user message")
    feedback = models.BooleanField(null=True, blank=True, help_text="User feedback: True=helpful, False=not helpful")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{'Bot' if self.is_bot else 'User'}: {self.message[:50]}"