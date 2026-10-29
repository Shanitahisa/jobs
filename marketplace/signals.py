import uuid
from django.db.models.signals import pre_save,post_save,post_delete
from django.dispatch import receiver
from .models import Profile,Opportunity,Business,Document,Interest,Shortlist,Engagement,Review,Payment
from .notifications import notify,admins,matching_opportunity,matching_profile,after_commit

TRACKED=[Business,Document,Opportunity,Engagement,Payment]

@receiver(pre_save)
def previous_state(sender,instance,raw=False,**kwargs):
    if sender in TRACKED and not raw:
        instance._previous=sender.objects.filter(pk=instance.pk).values().first() if instance.pk else None

@receiver(post_save,sender=Profile)
def profile_saved(sender,instance,created,raw=False,**kwargs):
    if raw:return
    if created:after_commit(lambda:notify(instance.user,'system','Welcome to Gig House','Your next chapter starts here. Complete your profile or business details to get started.',{'page':'profile' if instance.role=='worker' else 'business'},'welcome'))
    if instance.role=='worker' and instance.published:after_commit(lambda:matching_profile(instance.pk))

@receiver(post_save,sender=Opportunity)
def opportunity_saved(sender,instance,created,raw=False,**kwargs):
    if raw:return
    previous=getattr(instance,'_previous',None)
    relevant=['status','skills','preferred_skills','profession','availability','location','remote','start_date','end_date','minimum_experience','required_certificate','required_clearance','work_type']
    if created or not previous or any(previous[k]!=getattr(instance,k) for k in relevant):after_commit(lambda:matching_opportunity(instance.pk))
    changed=not created and previous and any(previous[k]!=getattr(instance,k) for k in relevant+['budget','description','deliverables'])
    if changed:
        def update_interested():
            title='An opportunity you followed has closed' if instance.status=='closed' else 'An opportunity brief was updated'
            message=f'{instance.title}. Open your interests to review the latest status and requirements. Accepted agreements keep their original terms.'
            event=f'opportunity-update:{instance.pk}:{uuid.uuid4().hex}'
            for interest in instance.interests.select_related('worker'):
                notify(interest.worker,'activity',title,message,{'page':'interests','opportunity_id':instance.pk},event)
        after_commit(update_interested)

@receiver(post_save,sender=Business)
def business_saved(sender,instance,created,raw=False,**kwargs):
    if raw:return
    previous=getattr(instance,'_previous',None)
    if not created and previous and previous['status']==instance.status:return
    status=instance.status
    if status in ['approved','changes','rejected']:
        message={'approved':'Your business has been approved. You can now publish opportunities and send offers.','changes':'Your business needs an update. Open your business page to read the admin feedback.','rejected':'Your business review is complete. Open your business page for the review outcome.'}[status]
        after_commit(lambda:notify(instance.owner,'system','Business verification updated',message,{'page':'business'},f'business:{instance.pk}:{status}:{uuid.uuid4().hex}'))
        if status=='approved':
            def match_existing():
                for pk in instance.opportunities.filter(status='open').values_list('pk',flat=True):matching_opportunity(pk)
            after_commit(match_existing)
    if status=='pending':after_commit(lambda:admins('A business is ready for review',f'{instance.name} submitted business documents. Review the submission in administration.',{'page':'business','admin':True},f'business-submitted:{instance.pk}:{uuid.uuid4().hex}'))

@receiver(post_save,sender=Document)
def document_saved(sender,instance,created,raw=False,**kwargs):
    if raw:return
    previous=getattr(instance,'_previous',None)
    if created:
        after_commit(lambda:admins('A document needs review','A user has uploaded a private document. Review it securely in administration.',{'page':'documents','admin':True},f'document-upload:{instance.pk}'))
    elif previous and previous['status']!=instance.status:
        after_commit(lambda:notify(instance.owner,'system','Your document review was updated','Open your private documents to view the review status. No document contents are included in this notification.',{'page':'documents'},f'document-status:{instance.pk}:{instance.status}:{uuid.uuid4().hex}'))
        if instance.status=='verified' and hasattr(instance.owner,'profile') and instance.owner.profile.role=='worker':after_commit(lambda:matching_profile(instance.owner.profile.pk))

@receiver(post_save,sender=Interest)
def interest_saved(sender,instance,created,raw=False,**kwargs):
    if raw or not created:return
    after_commit(lambda:notify(instance.opportunity.business.owner,'activity','Someone is interested in your opportunity',f'{instance.worker.profile.name} expressed interest in {instance.opportunity.title}. View their introduction and profile.',{'page':'interests','opportunity_id':instance.opportunity_id},f'interest:{instance.pk}'))

@receiver(post_delete,sender=Interest)
def interest_withdrawn(sender,instance,**kwargs):
    interest_id=instance.pk
    def send():
        opp=Opportunity.objects.select_related('business__owner').filter(pk=instance.opportunity_id).first()
        if opp:notify(opp.business.owner,'activity','An expression of interest was withdrawn',f'A candidate withdrew their interest in {opp.title}. Your interested-talent list has been updated.',{'page':'interests','opportunity_id':opp.pk},f'interest-withdrawn:{interest_id}')
    after_commit(send)

@receiver(post_save,sender=Shortlist)
def shortlist_saved(sender,instance,created,raw=False,**kwargs):
    if raw or not created:return
    after_commit(lambda:notify(instance.worker,'activity','You made the shortlist',f'{instance.opportunity.business.name} shortlisted you for {instance.opportunity.title}. This is an invitation to stay connected, not a confirmed offer.',{'page':'opportunities','opportunity_id':instance.opportunity_id},f'shortlist:{instance.pk}'))

@receiver(post_save,sender=Engagement)
def engagement_saved(sender,instance,created,raw=False,**kwargs):
    if raw:return
    previous=getattr(instance,'_previous',None)
    old=previous['status'] if previous else None
    if not created and old==instance.status:return
    worker=instance.worker;employer=instance.opportunity.business.owner
    status=instance.status;target={'page':'gigs','engagement_id':instance.pk}
    transitions={
        'offered':([worker],'You have a new offer','Review the amount, dates and deliverables, then accept or decline.'),
        'accepted':([employer],'Your offer was accepted','The worker accepted. You can now confirm gig funding.'),
        'hired':([worker,employer],'Hiring is confirmed','The offer has been accepted by both sides. Employment administration happens outside this prototype.'),
        'funded':([worker],'Changes were requested' if old=='submitted' else 'Payment record updated','Review the requested changes before resubmitting.' if old=='submitted' else ('A test funding record is ready. Review it in Payments before starting work.' if instance.payment_mode=='demo' else 'Your sandbox collection was verified. Review the transaction in Payments.')),
        'submitted':([employer],'Work is ready for your review','The worker submitted delivery notes. Review the result and approve it or request changes.'),
        'approved':([worker],'Your work was approved','The employer approved your submission. Payout is a separate step and is not confirmed yet.'),
        'completed':([worker,employer],'Your gig is complete','Your workflow is complete. Review the test payout record in Payments and leave a review.' if instance.payment_mode=='demo' else 'The sandbox payout was verified. Review it in Payments and leave a review.'),
        'disputed':([worker,employer],'An issue was reported on your gig','The engagement is paused for admin review. Open the gig for details.'),
        'cancelled':([worker,employer],'An offer was cancelled','The offer was declined or cancelled before work began.'),
    }
    if status not in transitions:return
    users,title,message=transitions[status]
    event=f'engagement:{instance.pk}:{status}:{uuid.uuid4().hex}'
    category='payment' if status in ['funded','completed'] and old!='submitted' else 'activity'
    for user in users:after_commit(lambda u=user:notify(u,category,title,f'{instance.opportunity.title}. {message}',target,event))
    if status=='disputed':after_commit(lambda:admins('A gig needs dispute review',f'Engagement #{instance.pk} was flagged by a participant. Review it in administration.',{'page':'gigs','admin':True},event+'-admin'))

@receiver(post_save,sender=Review)
def review_saved(sender,instance,created,raw=False,**kwargs):
    if raw or not created:return
    eng=instance.engagement
    def send():
        other=eng.opportunity.business.owner if instance.author_id==eng.worker_id else eng.worker
        shared=eng.reviews.count()>=2
        users=[eng.worker,eng.opportunity.business.owner] if shared else [other]
        for user in users:notify(user,'activity','Your reviews are ready' if shared else 'Your collaborator left a review','Both reviews are now available in your engagement.' if shared else 'Leave your own honest review to reveal both reviews. Ratings and comments stay private until then.',{'page':'gigs','engagement_id':eng.pk},f'review:{instance.pk}')
    after_commit(send)

@receiver(post_save,sender=Payment)
def payment_saved(sender,instance,created,raw=False,**kwargs):
    if raw or instance.mode!='sandbox_payout':return
    previous=getattr(instance,'_previous',None)
    if previous and previous['status']==instance.status:return
    eng=instance.engagement
    if instance.status=='payout_pending':
        after_commit(lambda:notify(eng.worker,'payment','A sandbox payout is processing',f'{eng.opportunity.title}. The transfer was initiated; completion still needs verification. Review its status in Payments.',{'page':'gigs','engagement_id':eng.pk},f'payout-pending:{instance.pk}'))
    elif instance.status in ['payout_failed','payout_rejected','reconcile_required']:
        for user in [eng.worker,eng.opportunity.business.owner]:
            after_commit(lambda u=user:notify(u,'payment','A sandbox payment needs attention',f'{eng.opportunity.title}. The payout could not be confirmed. Please ask admin to reconcile it before retrying.',{'page':'gigs','engagement_id':eng.pk},f'payout-issue:{instance.pk}:{instance.status}'))
        after_commit(lambda:admins('Sandbox payment reconciliation required',f'Payment #{instance.pk} needs review. Check provider records before retrying.',{'page':'gigs','admin':True},f'payment-admin:{instance.pk}:{instance.status}'))
