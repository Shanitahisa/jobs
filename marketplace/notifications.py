import logging
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from .models import Notification,NotificationPreference,EmailDelivery,Profile,Opportunity
from .matching import match

logger=logging.getLogger(__name__)

def notify(user,category,title,message,target,event_key):
    pref,_=NotificationPreference.objects.get_or_create(user=user)
    enabled=getattr(pref,{'opportunity':'opportunity_alerts','payment':'payment_alerts'}.get(category,'activity_alerts'))
    if not enabled:return None
    with transaction.atomic():
        notification,created=Notification.objects.get_or_create(event_key=f'{event_key}:u{user.pk}',defaults={'user':user,'category':category,'title':title,'message':message,'target':target})
        if created and pref.email_enabled:
            EmailDelivery.objects.create(notification=notification)
    return notification

def admins(title,message,target,event_key):
    for user in User.objects.filter(is_staff=True,is_active=True):notify(user,'system',title,message,target,event_key)

def matching_opportunity(pk):
    opportunity=Opportunity.objects.select_related('business').filter(pk=pk,status='open',business__status='approved',business__owner__is_active=True).first()
    if not opportunity or opportunity.end_date<timezone.localdate():return
    for profile in Profile.objects.filter(role='worker',published=True,user__is_active=True).select_related('user'):
        result=match(profile,opportunity)
        if result['eligible']:
            notify(profile.user,'opportunity','A new opportunity fits your skills',f'{opportunity.title} at {opportunity.business.name}. Your skills, availability and essential requirements align. Review the brief before expressing interest.',{'page':'opportunities','opportunity_id':pk},f'opportunity-match:{pk}')

def matching_profile(pk):
    profile=Profile.objects.select_related('user').filter(pk=pk,role='worker',published=True,user__is_active=True).first()
    if not profile:return
    for opportunity in Opportunity.objects.filter(status='open',business__status='approved',business__owner__is_active=True,end_date__gte=timezone.localdate()).select_related('business'):
        if match(profile,opportunity)['eligible']:
            notify(profile.user,'opportunity','An opportunity fits your profile',f'{opportunity.title} at {opportunity.business.name} matches your current skills and preferences. Explore the brief and decide whether it is right for you.',{'page':'opportunities','opportunity_id':opportunity.pk},f'opportunity-match:{opportunity.pk}')

def after_commit(callback):
    # Notification errors must not roll back an already successful marketplace action.
    def safe():
        try:callback()
        except Exception:logger.exception('Notification event could not be recorded')
    transaction.on_commit(safe)
