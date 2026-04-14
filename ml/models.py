from django.db import models
from django.conf import settings

class ManifestoSentiment(models.Model):
    """Store sentiment analysis of candidate manifestos."""
    candidate = models.OneToOneField('voting.Candidate', on_delete=models.CASCADE, related_name='manifesto_sentiment')
    polarity = models.FloatField(null=True, blank=True)   # -1 (negative) to +1 (positive)
    subjectivity = models.FloatField(null=True, blank=True)  # 0 (objective) to 1 (subjective)
    analysis_date = models.DateTimeField(auto_now_add=True)

class FeedbackSentiment(models.Model):
    """Store sentiment analysis of user feedback comments."""
    feedback = models.OneToOneField('voting.Feedback', on_delete=models.CASCADE, related_name='sentiment')
    polarity = models.FloatField(null=True, blank=True)
    subjectivity = models.FloatField(null=True, blank=True)
    analysis_date = models.DateTimeField(auto_now_add=True)

class AnomalyAlert(models.Model):
    """Store detected anomalies in voting patterns."""
    election = models.ForeignKey('voting.Election', on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=50, choices=[
        ('ip_concentration', 'IP Concentration'),
        ('rapid_votes', 'Rapid Votes'),
        ('geo_outlier', 'Geographic Outlier'),
    ])
    description = models.TextField()
    severity = models.IntegerField(choices=[(1,'Low'),(2,'Medium'),(3,'High')], default=1)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)