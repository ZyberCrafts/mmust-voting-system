from django.apps import AppConfig

class MlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ml'

    def ready(self):
        # Optionally register signals to auto-analyze new objects if feature enabled
        from django.conf import settings
        if 'manifesto_analysis' in getattr(settings, 'AI_ENABLED_FEATURES', []):
            from django.db.models.signals import post_save
            from voting.models import Candidate
            from .tasks import analyze_manifesto_for_candidate
            post_save.connect(analyze_manifesto_for_candidate, sender=Candidate)