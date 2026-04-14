from django.db import models
from django.conf import settings
from voting.models import Election, Candidate

class ManifestoItem(models.Model):
    """A single promise or agenda item from a candidate's manifesto."""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='manifesto_items')
    description = models.TextField(help_text="The promise or agenda item")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['candidate', 'order']

    def __str__(self):
        return f"{self.candidate.user.get_full_name()}: {self.description[:50]}"

class RatingSession(models.Model):
    """A specific rating period (e.g., monthly) for a leader."""
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='rating_sessions')
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.election.name} - {self.start_date.date()}"

class LeaderRating(models.Model):
    """Rating given by a user on a manifesto item for a specific session."""
    session = models.ForeignKey(RatingSession, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item = models.ForeignKey(ManifestoItem, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=[(i, str(i)) for i in range(1, 6)], help_text="1-5 stars")
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['session', 'user', 'item']  # prevent duplicate ratings per user per item
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.item} - {self.rating}"

class NotificationLog(models.Model):
    """Track sent reminders to avoid duplicates."""
    session = models.ForeignKey(RatingSession, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=20, choices=[('email', 'Email'), ('sms', 'SMS')])