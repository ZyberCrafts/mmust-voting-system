# voting/apps.py

from django.apps import AppConfig

class VotingConfig(AppConfig):
    """
    Configuration for the voting app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'voting'
    verbose_name = 'Voting System'

    def ready(self):
        """
        Import signal handlers when the app is ready.
        """
        import voting.signals  # noqa: F401