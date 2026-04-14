from celery import shared_task
import logging
from django.conf import settings
from .models import ManifestoSentiment, FeedbackSentiment, AnomalyAlert
from .services import analyze_manifesto, analyze_feedback, detect_anomalies, predict_turnout
from voting.models import Candidate, Feedback

logger = logging.getLogger(__name__)

@shared_task
def analyze_all_manifestos():
    """Run on candidate creation/update."""
    for candidate in Candidate.objects.filter(manifesto__isnull=False):
        polarity, subjectivity = analyze_manifesto(candidate.manifesto)
        if polarity is not None:
            ManifestoSentiment.objects.update_or_create(
                candidate=candidate,
                defaults={'polarity': polarity, 'subjectivity': subjectivity}
            )

@shared_task
def analyze_all_feedback():
    for fb in Feedback.objects.all():
        polarity, subjectivity = analyze_feedback(fb.comment)
        if polarity is not None:
            FeedbackSentiment.objects.update_or_create(
                feedback=fb,
                defaults={'polarity': polarity, 'subjectivity': subjectivity}
            )

@shared_task
def run_anomaly_detection(election_id):
    alerts = detect_anomalies(election_id)
    for alert in alerts:
        alert.save()
    logger.info(f"Detected {len(alerts)} anomalies for election {election_id}")

@shared_task
def predict_turnout_for_election(election_id):
    predicted = predict_turnout(election_id)
    logger.info(f"Predicted final turnout for election {election_id}: {predicted}%")
    
@shared_task
def analyze_manifesto_for_candidate(candidate_id):
    """Run sentiment analysis on a single candidate's manifesto."""
    try:
        candidate = Candidate.objects.get(id=candidate_id)
        polarity, subjectivity = analyze_manifesto(candidate.manifesto)
        if polarity is not None:
            ManifestoSentiment.objects.update_or_create(
                candidate=candidate,
                defaults={'polarity': polarity, 'subjectivity': subjectivity}
            )
    except Candidate.DoesNotExist:
        logger.error(f"Candidate {candidate_id} not found")