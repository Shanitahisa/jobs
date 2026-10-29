from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view,permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from .models import Business,Document,Opportunity,Engagement,Payment,EmailDelivery,AdminAudit,Profile
from .serializers import BusinessSerializer,DocumentSerializer,OpportunitySerializer,EngagementSerializer
from .workspace_views import payment_record
from .views import error
from django.shortcuts import get_object_or_404


def audit(request,action,obj,note,**details):
    AdminAudit.objects.create(actor=request.user,action=action,record_type=obj._meta.model_name,record_id=obj.pk,note=note,details=details)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def overview(request):
    return Response({'users':User.objects.count(),'active_users':User.objects.filter(is_active=True).count(),'workers':Profile.objects.filter(role='worker').count(),'businesses':Business.objects.count(),'pending_businesses':Business.objects.filter(status='pending').count(),'pending_documents':Document.objects.filter(status='pending').count(),'open_opportunities':Opportunity.objects.filter(status='open').count(),'engagements':Engagement.objects.count(),'disputes':Engagement.objects.filter(status='disputed').count(),'payments':Payment.objects.count(),'emails_queued':EmailDelivery.objects.filter(status__in=['queued','retry']).count(),'emails_failed':EmailDelivery.objects.filter(status__in=['failed','uncertain']).count()})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def businesses(request):
    data=[]
    for obj in Business.objects.select_related('owner__profile').order_by('-id')[:300]:
        row=BusinessSerializer(obj).data
        row.update(owner_name=obj.owner.profile.name,owner_email=obj.owner.email,documents=DocumentSerializer(Document.objects.filter(owner=obj.owner,kind__in=['registration','licence']),many=True).data)
        data.append(row)
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def review_business(request,pk):
    status=request.data.get('status');note=str(request.data.get('note','')).strip()[:3000]
    if status not in ['approved','changes','rejected']:return error('Choose approved, changes requested or rejected.')
    if status!='approved' and not note:return error('Include a helpful reason for this decision.')
    with transaction.atomic():
        obj=get_object_or_404(Business.objects.select_for_update(),pk=pk)
        if status=='approved':
            if obj.status not in ['pending','changes']:return error('Only submitted businesses can be approved.')
            kinds=set(Document.objects.filter(owner=obj.owner,kind__in=['registration','licence'],status__in=['pending','verified']).values_list('kind',flat=True))
            if not {'registration','licence'}.issubset(kinds):return error('Registration and licence documents are required before approval.')
        before=obj.status;obj.status=status;obj.review_note=note or 'Business verification approved.';obj.save()
        audit(request,'business_review',obj,obj.review_note,before=before,after=status)
    return Response(BusinessSerializer(obj).data)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def documents(request):
    data=[]
    for obj in Document.objects.select_related('owner__profile').order_by('-id')[:300]:
        row=DocumentSerializer(obj).data;row.update(owner_name=obj.owner.profile.name,owner_email=obj.owner.email)
        data.append(row)
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def review_document(request,pk):
    status=request.data.get('status');note=str(request.data.get('note','')).strip()[:3000]
    if status not in ['verified','rejected','pending']:return error('Choose verified, rejected or pending.')
    if status=='rejected' and not note:return error('Include a reason so the user can correct their document.')
    with transaction.atomic():
        obj=get_object_or_404(Document.objects.select_for_update(),pk=pk)
        if status=='verified' and obj.expires and obj.expires<timezone.localdate():return error('An expired document cannot be verified.')
        before=obj.status;obj.status=status;obj.review_note=note;obj.save()
        audit(request,'document_review',obj,note,before=before,after=status)
    return Response(DocumentSerializer(obj).data)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def users(request):
    data=[]
    for obj in User.objects.select_related('profile').order_by('-id')[:300]:
        p=getattr(obj,'profile',None)
        data.append({'id':obj.pk,'name':p.name if p else obj.username,'email':obj.email,'role':'admin' if obj.is_staff else p.role if p else 'user','is_active':obj.is_active,'is_staff':obj.is_staff,'joined':obj.date_joined,'published':p.published if p else False})
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def user_status(request,pk):
    active=request.data.get('active');note=str(request.data.get('note','')).strip()[:3000]
    if type(active) is not bool:return error('Active must be true or false.')
    if not note:return error('Record a reason for this account action.')
    with transaction.atomic():
        obj=get_object_or_404(User.objects.select_for_update(),pk=pk)
        if obj.is_staff or obj.pk==request.user.pk:return error('Staff accounts cannot be suspended through this interface.',403)
        before=obj.is_active;obj.is_active=active;obj.save(update_fields=['is_active'])
        if not active:Token.objects.filter(user=obj).delete()
        audit(request,'user_activated' if active else 'user_suspended',obj,note,before=before,after=active)
    return Response({'detail':'Account status updated.'})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def opportunities(request):
    return Response(OpportunitySerializer(Opportunity.objects.select_related('business').order_by('-id')[:300],many=True).data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def moderate_opportunity(request,pk):
    status=request.data.get('status');note=str(request.data.get('note','')).strip()[:3000]
    if status not in ['open','closed'] or not note:return error('Choose an opportunity status and record a reason.')
    with transaction.atomic():
        obj=get_object_or_404(Opportunity.objects.select_for_update(),pk=pk)
        if status=='open' and obj.business.status!='approved':return error('Only approved businesses can have open opportunities.')
        before=obj.status;obj.status=status;obj.save();audit(request,'opportunity_moderation',obj,note,before=before,after=status)
    return Response({'detail':'Opportunity updated.'})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def engagements(request):
    qs=Engagement.objects.select_related('worker__profile','opportunity__business').order_by('-id')[:300]
    return Response(EngagementSerializer(qs,many=True,context={'request':request}).data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def resolve_dispute(request,pk):
    action=request.data.get('action');note=str(request.data.get('note','')).strip()[:3000]
    if action not in ['resume_work','return_to_review'] or not note:return error('Choose a resolution and include a note for both participants.')
    with transaction.atomic():
        obj=get_object_or_404(Engagement.objects.select_for_update(),pk=pk,status='disputed')
        if action=='resume_work' and not obj.payments.filter(status__in=['verified','collection_simulated']).exists():return error('Funding must be reconciled before work can resume.')
        if action=='return_to_review' and not obj.submission:return error('There is no submitted work to review.')
        obj.status='funded' if action=='resume_work' else 'submitted';obj.note=note;obj.save()
        audit(request,'dispute_resolved',obj,note,after=obj.status)
        from .notifications import after_commit,notify
        for user in [obj.worker,obj.opportunity.business.owner]:
            after_commit(lambda u=user:notify(u,'activity','An admin reviewed your gig issue',f'{obj.opportunity.title}. Open the engagement to review the resolution and next steps.',{'page':'gigs','engagement_id':obj.pk},f'dispute-resolved:{obj.pk}:{timezone.now().timestamp()}'))
    return Response({'detail':'Resolution saved. No payment was released by this action.'})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def payments(request):
    return Response([payment_record(obj) for obj in Payment.objects.select_related('engagement__worker__profile','engagement__opportunity__business').order_by('-id')[:300]])


@api_view(['GET'])
@permission_classes([IsAdminUser])
def emails(request):
    return Response([{'id':obj.pk,'title':obj.notification.title,'recipient':obj.notification.user.email,'status':obj.status,'attempts':obj.attempts,'last_error':obj.last_error,'message_id':obj.provider_id,'created_at':obj.created_at} for obj in EmailDelivery.objects.select_related('notification__user').order_by('-id')[:300]])


@api_view(['POST'])
@permission_classes([IsAdminUser])
def retry_email(request,pk):
    with transaction.atomic():
        obj=get_object_or_404(EmailDelivery.objects.select_for_update(),pk=pk)
        if obj.status not in ['failed','retry']:return error('Only confirmed failed messages can be retried. Uncertain sends require reconciliation.')
        before=obj.status;obj.status='queued';obj.attempts=0;obj.next_attempt=timezone.now();obj.last_error='';obj.save()
        audit(request,'email_retry',obj,'Admin requested retry after review.',before=before)
    return Response({'detail':'Email queued for retry.'})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def audit_log(request):
    return Response([{'id':obj.pk,'actor':obj.actor.username if obj.actor else 'Removed account','action':obj.action,'record_type':obj.record_type,'record_id':obj.record_id,'note':obj.note,'details':obj.details,'created_at':obj.created_at} for obj in AdminAudit.objects.select_related('actor').all()[:300]])
