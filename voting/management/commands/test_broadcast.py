from django.core.management.base import BaseCommand
from voting.models import User
from voting.tasks import send_notification_task

class Command(BaseCommand):
    help = 'Test broadcast to a single email address'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Recipient email')
        parser.add_argument('--subject', type=str, default='Test Broadcast', help='Email subject')

    def handle(self, *args, **options):
        email = options['email']
        subject = options['subject']
        try:
            user = User.objects.get(email=email)
            send_notification_task.delay(user.id, subject, 'This is a test broadcast message.', send_email=True, send_sms=False)
            self.stdout.write(self.style.SUCCESS(f'Broadcast sent to {email}'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User with email {email} not found'))