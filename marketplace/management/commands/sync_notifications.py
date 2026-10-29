from django.core.management.base import BaseCommand
from marketplace.models import Opportunity
from marketplace.notifications import matching_opportunity

class Command(BaseCommand):
    help='Create deduplicated match alerts for existing open opportunities.'
    def handle(self,*args,**kwargs):
        for pk in Opportunity.objects.filter(status='open',business__status='approved').values_list('pk',flat=True):matching_opportunity(pk)
        self.stdout.write('Existing opportunity matches synchronised without duplicate alerts.')
