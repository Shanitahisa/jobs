import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone
from marketplace.email_service import process_outbox
from marketplace.models import Document
from marketplace.notifications import notify

class Command(BaseCommand):
    help='Process the durable SMTP email outbox and credential-expiry reminders. Never sends fictional demo addresses.'
    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true')
        parser.add_argument('--interval',type=int,default=10)
    def handle(self,*args,**options):
        last_scan=None
        try:
            while True:
                close_old_connections()
                if last_scan is None or time.monotonic()-last_scan>3600 or options['once']:
                    today=timezone.localdate()
                    for doc in Document.objects.filter(status='verified',expires__isnull=False,expires__lte=today+timedelta(days=7)).select_related('owner'):
                        expired=doc.expires<today
                        notify(doc.owner,'system','A verified document has expired' if expired else 'A verified document expires soon','Open your private documents to review the expiry date and upload updated evidence. No private document details are included here.',{'page':'documents'},f'document-expiry:{doc.pk}:{doc.expires}:{expired}')
                    last_scan=time.monotonic()
                result=process_outbox()
                if result['processed'] or options['once']:self.stdout.write(str(result))
                if options['once']:break
                time.sleep(max(3,options['interval']))
        except KeyboardInterrupt:self.stdout.write('Notification worker stopped.')
