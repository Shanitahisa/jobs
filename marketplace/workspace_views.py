from pathlib import Path
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view,permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Profile,Document,Engagement,SubmissionAttachment,Payment
from .serializers import ProfileSerializer,SubmissionAttachmentSerializer
from .uploads import image_file,submission_file
from .views import error,require_role


@api_view(['POST','DELETE'])
def profile_photo(request):
    profile=request.user.profile
    if request.method=='DELETE':profile.photo='';profile.save(update_fields=['photo'])
    else:
        content=image_file(request.FILES.get('file'))
        profile.photo.save(content.name,content)
    return Response(ProfileSerializer(profile).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def view_profile_photo(request,user_id):
    profile=get_object_or_404(Profile,user_id=user_id,user__is_active=True)
    own=request.user.is_authenticated and (request.user.id==user_id or request.user.is_staff)
    public=profile.published or (profile.role=='employer' and hasattr(profile.user,'business') and profile.user.business.status=='approved')
    if not profile.photo or not (own or public):return error('Profile photo is not available.',404)
    response=FileResponse(profile.photo.open('rb'),content_type='image/jpeg');response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    return response


@api_view(['GET'])
@permission_classes([AllowAny])
def public_profile(request,slug):
    profile=get_object_or_404(Profile,page_slug=slug,role='worker',published=True,user__is_active=True)
    data=ProfileSerializer(profile).data
    public={k:data[k] for k in ['name','headline','bio','location','availability','work_types','professions','experience','rate','portfolio','projects','work_history','photo_url','page_slug','page_url']}
    public['credentials']=[{'kind':d.kind,'profession':d.profession,'skill':d.skill,'expires':d.expires} for d in Document.objects.filter(owner=profile.user,status='verified',kind__in=['certificate','clearance']) if not d.expires or d.expires>=timezone.localdate()]
    return Response(public)


def participant(eng,user):return user.is_staff or user.id in [eng.worker_id,eng.opportunity.business.owner_id]


@api_view(['GET','POST'])
def submission_attachments(request,pk):
    eng=get_object_or_404(Engagement,pk=pk)
    if not participant(eng,request.user):return error('This engagement is private.',403)
    if request.method=='GET':
        qs=eng.attachments.order_by('id')
        if request.user.id!=eng.worker_id and not request.user.is_staff:qs=qs.filter(submission__isnull=False)
        return Response(SubmissionAttachmentSerializer(qs,many=True).data)
    require_role(request.user,'worker')
    with transaction.atomic():
        eng=Engagement.objects.select_for_update().get(pk=eng.pk)
        if eng.worker_id!=request.user.id:return error('Only the assigned worker can upload delivery files.',403)
        if eng.status!='funded':return error('Files can be uploaded when work is in progress or changes were requested.')
        if eng.attachments.filter(submission__isnull=True).count()>=10:return error('Each submission can include up to 10 files.')
        content,name,kind,size=submission_file(request.FILES.get('file'))
        obj=SubmissionAttachment(engagement=eng,uploader=request.user,name=name,kind=kind,size=size)
        obj.file.save(content.name,content)
    return Response(SubmissionAttachmentSerializer(obj).data,status=201)


@api_view(['GET','DELETE'])
def submission_attachment(request,pk):
    obj=get_object_or_404(SubmissionAttachment.objects.select_related('engagement__opportunity__business'),pk=pk)
    if not participant(obj.engagement,request.user):return error('This delivery file is private.',403)
    if request.method=='DELETE':
        with transaction.atomic():
            eng=Engagement.objects.select_for_update().get(pk=obj.engagement_id)
            obj=SubmissionAttachment.objects.get(pk=obj.pk)
            if obj.uploader_id!=request.user.id or obj.submission_id or eng.status!='funded':return error('Only your unsubmitted draft files can be removed.',403)
            obj.delete()
        return Response({'detail':'Draft attachment removed.'})
    if not obj.submission_id and request.user.id!=obj.uploader_id and not request.user.is_staff:return error('This file has not been submitted.',403)
    response=FileResponse(obj.file.open('rb'),as_attachment=obj.kind!='image',filename=obj.name,content_type='image/jpeg' if obj.kind=='image' else 'application/octet-stream')
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    return response


def payment_record(obj):
    eng=obj.engagement
    return {'id':obj.pk,'engagement_id':eng.pk,'title':eng.opportunity.title,'worker_name':eng.worker.profile.name,'business_name':eng.opportunity.business.name,'worker_id':eng.worker_id,'employer_id':eng.opportunity.business.owner_id,'reference':obj.reference,'amount':str(obj.amount),'status':obj.status,'mode':obj.mode,'direction':'payout' if obj.mode=='sandbox_payout' or obj.status=='payout_simulated' else 'collection','created_at':obj.created_at}


@api_view(['GET'])
def payments(request):
    qs=Payment.objects.filter(Q(engagement__worker=request.user)|Q(engagement__opportunity__business__owner=request.user)).select_related('engagement__worker__profile','engagement__opportunity__business').order_by('-created_at')
    return Response([payment_record(obj) for obj in qs[:300]])


def person_data(profile,detail=False):
    user=profile.user
    row={'id':user.pk,'name':profile.name,'role':'admin' if user.is_staff else profile.role,'headline':profile.headline,'location':profile.location,'photo_url':ProfileSerializer(profile).data['photo_url'] if profile.published or (profile.role=='employer' and hasattr(user,'business') and user.business.status=='approved') else None,'published':profile.published,'page_url':ProfileSerializer(profile).data['page_url']}
    if detail:
        row['bio']=profile.bio if profile.published else ''
        if profile.role=='worker' and profile.published:
            data=ProfileSerializer(profile).data
            row.update({k:data[k] for k in ['availability','work_types','professions','experience','rate','portfolio','projects','work_history']})
        if profile.role=='employer' and hasattr(user,'business') and user.business.status=='approved':
            business=user.business
            row['business']={'name':business.name,'industry':business.industry,'location':business.location,'description':business.description,'website':business.website,'verified':True}
    return row


@api_view(['GET'])
def people(request):
    query=str(request.query_params.get('q','')).strip()[:120]
    role=request.query_params.get('role','')
    qs=Profile.objects.filter(user__is_active=True).select_related('user','user__business')
    if query:qs=qs.filter(Q(name__icontains=query)|Q(headline__icontains=query)|Q(location__icontains=query)|Q(user__business__name__icontains=query)|Q(published=True,professions__icontains=query))
    if role in ['worker','employer']:qs=qs.filter(role=role,user__is_staff=False)
    rows=[person_data(p) for p in qs.order_by('name','id')[:60]]
    return Response({'items':rows,'limit':60})


@api_view(['GET'])
def person(request,pk):
    profile=get_object_or_404(Profile.objects.select_related('user','user__business'),user_id=pk,user__is_active=True)
    return Response(person_data(profile,True))
