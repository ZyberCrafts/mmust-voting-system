from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

class AttackLog(models.Model):
    ATTACK_TYPES = (
        ('bruteforce', 'Brute Force'),
        ('sqli', 'SQL Injection'),
        ('xss', 'Cross‑Site Scripting'),
        ('idor', 'Insecure Direct Object Reference'),
        ('dos', 'Denial of Service'),
        ('unknown', 'Unknown'),
    )
    SEVERITY = (
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Critical'),
    )

    timestamp = models.DateTimeField(auto_now_add=True)
    attack_type = models.CharField(max_length=20, choices=ATTACK_TYPES)
    severity = models.IntegerField(choices=SEVERITY, default=1)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    username = models.CharField(max_length=150, blank=True, help_text="Username if authenticated")
    user_id = models.IntegerField(null=True, blank=True, help_text="User ID if authenticated")
    request_path = models.CharField(max_length=500)
    request_method = models.CharField(max_length=10)
    request_data = models.TextField(blank=True, help_text="Relevant request data (sanitized)")
    description = models.TextField(blank=True)
    blocked = models.BooleanField(default=False, help_text="Was the request blocked?")
    resolved = models.BooleanField(default=False)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['attack_type', 'severity']),
        ]

    def __str__(self):
        return f"{self.get_attack_type_display()} from {self.ip_address} at {self.timestamp}"