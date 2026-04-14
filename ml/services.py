import logging
from django.conf import settings
from django.utils import timezone 
from .models import AnomalyAlert 
    
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Feature flags
# ------------------------------------------------------------------
ENABLED_FEATURES = getattr(settings, 'AI_ENABLED_FEATURES', [])

def is_feature_enabled(feature):
    return feature in ENABLED_FEATURES

# ------------------------------------------------------------------
# Face Recognition (Advanced)
# ------------------------------------------------------------------
def enhance_face_embedding(image_data):
    """Replace HOG with deep model – placeholder."""
    if not is_feature_enabled('face_deep'):
        return None
    # Here you would load a deep model (e.g., face_recognition) and extract embedding.
    # For now, return a mock.
    import numpy as np
    return np.random.rand(128).astype(np.float32).tobytes()

# ------------------------------------------------------------------
# Manifesto Analysis (NLP)
# ------------------------------------------------------------------
def analyze_manifesto(manifesto_text):
    """Return (polarity, subjectivity) using simple rule‑based or transformer."""
    if not is_feature_enabled('manifesto_analysis'):
        return None, None
    try:
        from textblob import TextBlob
        blob = TextBlob(manifesto_text)
        return blob.sentiment.polarity, blob.sentiment.subjectivity
    except ImportError:
        logger.warning("textblob not installed – skipping manifesto analysis")
        return None, None

# ------------------------------------------------------------------
# Feedback Sentiment
# ------------------------------------------------------------------
def analyze_feedback(comment):
    if not is_feature_enabled('feedback_sentiment'):
        return None, None
    try:
        from textblob import TextBlob
        blob = TextBlob(comment)
        return blob.sentiment.polarity, blob.sentiment.subjectivity
    except ImportError:
        logger.warning("textblob not installed – skipping feedback analysis")
        return None, None

# ------------------------------------------------------------------
# Anomaly Detection
# ------------------------------------------------------------------
def detect_anomalies(election_id):
    """Check for IP concentration, rapid votes, geographic outliers."""
    if not is_feature_enabled('anomaly_detection'):
        return []
    from voting.models import VoterStatus
    from collections import Counter
    alerts = []
    statuses = VoterStatus.objects.filter(election_id=election_id, has_voted=True)
    # 1. IP concentration
    ip_counts = Counter(statuses.values_list('ip_address', flat=True))
    for ip, count in ip_counts.items():
        if count > 10:  # threshold configurable
            alerts.append(AnomalyAlert(
                election_id=election_id,
                alert_type='ip_concentration',
                description=f"IP {ip} voted {count} times",
                severity=2
            ))
    # 2. Rapid votes – we would need timestamps in VoterStatus (already have voted_at)
    # (Implement if needed)
    return alerts

# ------------------------------------------------------------------
# Predictive Analytics (turnout prediction)
# ------------------------------------------------------------------
def predict_turnout(election_id):
    """Return predicted final turnout percentage."""
    if not is_feature_enabled('predictive_analytics'):
        return None
    from voting.models import Election, VoterStatus
    from datetime import timedelta
    election = Election.objects.get(id=election_id)
    now = timezone.now()
    if not election.is_ongoing():
        return None
    elapsed = (now - election.start_time).total_seconds()
    total = (election.end_time - election.start_time).total_seconds()
    ratio = min(elapsed / total, 1.0)
    current_votes = VoterStatus.objects.filter(election=election, has_voted=True).count()
    # Simple linear projection (improve later)
    predicted = current_votes / ratio if ratio > 0 else current_votes
    total_voters = VoterStatus.objects.filter(election=election).count()
    return min(100, (predicted / total_voters) * 100) if total_voters else 0