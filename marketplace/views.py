import re
import uuid
from decimal import Decimal
from pathlib import Path
import requests
from django.conf import settings
from django.contrib.auth import authenticate, logout as django_logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Profile, Business, Document, Opportunity, Interest, Shortlist, Engagement, Review, Payment, PayoutAccount, ProjectImage,Notification,NotificationPreference,WorkSubmission,SubmissionAttachment
from .serializers import ProfileSerializer, BusinessSerializer, DocumentSerializer, OpportunitySerializer, EngagementSerializer, ReviewSerializer,NotificationSerializer,NotificationPreferenceSerializer
from .matching import match
from .catalog import CATALOG


def error(message, code=400): return Response({'detail':message},status=code)


def account(user):
    return {'id':user.id,'email':user.email,'is_staff':user.is_staff,'profile':ProfileSerializer(user.profile).data,
            'business':BusinessSerializer(user.business).data if hasattr(user,'business') else None}


def require_role(user, role):
    if not hasattr(user,'profile') or user.profile.role != role:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied(f'This action requires a {role} account.')


@api_view(['GET'])
@permission_classes([AllowAny])
def catalog(request):
    return Response({'categories':CATALOG,'demo_payments':settings.DEMO_PAYMENTS,'flutterwave_configured':bool(settings.FLUTTERWAVE_SECRET_KEY)})


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def register(request):
    email = str(request.data.get('email','')).strip().lower()
    name = serializers.CharField(max_length=120).run_validation(request.data.get('name','')).strip()
    role = request.data.get('role')
    password = serializers.CharField(max_length=4096,trim_whitespace=False).run_validation(request.data.get('password',''))
    confirmation=request.data.get('confirm_password')
    if confirmation is None:return error('Confirm your password.')
    if password!=confirmation:return error('Passwords do not match.')
    serializers.EmailField(max_length=150).run_validation(email)
    if not name or role not in ['worker','employer']: return error('Name and a valid account type are required.')
    if User.objects.filter(Q(email__iexact=email)|Q(username__iexact=email)).exists(): return error('An account with this email already exists.')
    try: validate_password(password,User(username=email,email=email,first_name=name))
    except DjangoValidationError as e: return error(' '.join(e.messages))
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=email,email=email,password=password)
            Profile.objects.create(user=user,name=name,role=role,work_types=['gig'])
            token = Token.objects.create(user=user)
            from .notifications import notify
            notify(user,'system','Welcome to Gig House!',f'Hi {name}, your account is ready. Complete your profile and discover your next opportunity.' if role=='worker' else f'Hi {name}, your account is ready. Add your business details to start connecting with talent.',{'page':'profile' if role=='worker' else 'business'},'welcome')
    except IntegrityError:
        if User.objects.filter(Q(email__iexact=email)|Q(username__iexact=email)).exists():return error('An account with this email already exists.')
        raise
    return Response({'token':token.key,'user':account(user)},status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def login(request):
    email=str(request.data.get('email','')).strip().lower()
    account_user=User.objects.filter(email__iexact=email).first() if email else None
    user = authenticate(username=account_user.username if account_user else email,password=request.data.get('password',''))
    if not user or not hasattr(user,'profile'): return error('Email or password is incorrect.',401)
    token,_ = Token.objects.get_or_create(user=user)
    return Response({'token':token.key,'user':account(user)})


@api_view(['POST'])
@permission_classes([AllowAny])
def logout(request):
    if request.user.is_authenticated:Token.objects.filter(user=request.user).delete()
    django_logout(request._request)
    return Response({'detail':'Signed out.'})


@api_view(['GET','PATCH'])
def me(request):
    if request.method == 'PATCH':
        serializer = ProfileSerializer(request.user.profile,data=request.data,partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response(account(request.user))


@api_view(['GET','POST','PATCH'])
def business(request):
    require_role(request.user,'employer')
    obj = getattr(request.user,'business',None)
    if request.method == 'GET': return Response(BusinessSerializer(obj).data if obj else None)
    serializer = BusinessSerializer(obj,data=request.data,partial=request.method=='PATCH' and obj is not None)
    serializer.is_valid(raise_exception=True)
    # Any material edit invalidates previous business verification.
    serializer.save(owner=request.user,status='draft',review_note='')
    return Response(serializer.data)


@api_view(['POST'])
def submit_business(request):
    obj = get_object_or_404(Business,owner=request.user)
    kinds = set(Document.objects.filter(owner=request.user,status__in=['pending','verified']).values_list('kind',flat=True))
    if not {'registration','licence'}.issubset(kinds): return error('Upload a registration certificate and trading licence before submitting.')
    obj.status='pending'; obj.review_note=''; obj.save()
    return Response(BusinessSerializer(obj).data)


@api_view(['GET','POST'])
def documents(request):
    if request.method=='GET': return Response(DocumentSerializer(Document.objects.filter(owner=request.user),many=True).data)
    uploaded = request.FILES.get('file')
    if not uploaded: return error('Select a document to upload.')
    if uploaded.size > 10*1024*1024: return error('Files must be 10 MB or smaller.')
    ext = Path(uploaded.name).suffix.lower()
    if ext not in ['.pdf','.jpg','.jpeg','.png','.txt']: return error('Use PDF, JPG, PNG or TXT files.')
    header = uploaded.read(12); uploaded.seek(0)
    valid = (ext=='.pdf' and header.startswith(b'%PDF-')) or (ext in ['.jpg','.jpeg'] and header.startswith(b'\xff\xd8\xff')) or (ext=='.png' and header.startswith(b'\x89PNG\r\n\x1a\n')) or ext=='.txt'
    if not valid: return error('The file contents do not match its extension.')
    serializer = DocumentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    kind = serializer.validated_data['kind']
    if serializer.validated_data.get('skill') and kind!='certificate':return error('Skills can only be linked to certifications.')
    if kind in ['registration','licence']: require_role(request.user,'employer')
    else: require_role(request.user,'worker')
    if kind in ['certificate','clearance'] and not serializer.validated_data.get('profession'):
        return error('Select the profession this document supports.')
    if kind in ['certificate','clearance'] and not any(serializer.validated_data['profession'] in items for items in CATALOG.values()):
        return error('Choose a supported profession.')
    doc = serializer.save(owner=request.user,file=uploaded)
    if kind in ['registration','licence'] and hasattr(request.user,'business'):
        Business.objects.filter(owner=request.user).update(status='draft',review_note='Documents changed. Submit for review again.')
    return Response(DocumentSerializer(doc).data,status=201)


@api_view(['GET'])
def download_document(request,pk):
    doc = get_object_or_404(Document,pk=pk)
    if doc.owner_id!=request.user.id and not request.user.is_staff: return error('This document is private.',403)
    response = FileResponse(doc.file.open('rb'),as_attachment=True,filename=Path(doc.file.name).name)
    response['X-Content-Type-Options']='nosniff'
    return response


@api_view(['POST'])
def parse_cv(request,pk):
    doc = get_object_or_404(Document,pk=pk,owner=request.user,kind='cv')
    try:
        if doc.file.name.lower().endswith('.pdf'):
            from pypdf import PdfReader
            with doc.file.open('rb') as f:
                reader=PdfReader(f)
                text='\n'.join((p.extract_text() or '') for p in list(reader.pages)[:10])[:30000]
        elif doc.file.name.lower().endswith('.txt'):
            with doc.file.open('rb') as f: text=f.read(100000).decode('utf-8',errors='replace')
        else: return error('Autofill supports text-based PDFs and TXT. Scanned files need manual entry.')
    except Exception: return error('Could not read this CV. Please complete your profile manually.')
    if not text.strip(): return error('No readable text found. Scanned CVs need manual entry.')
    professions=[]
    for category,items in CATALOG.items():
        for profession,skills in items.items():
            found=[s for s in skills if re.search(r'(?<!\w)'+re.escape(s)+r'(?!\w)',text,re.I)]
            if found: professions.append({'category':category,'profession':profession,'skills':found})
    years = re.search(r'(\d{1,2})\+?\s+years?',text,re.I)
    locations = ['Kampala','Entebbe','Jinja','Wakiso','Mbarara','Gulu']
    draft={'professions':professions[:5]}
    if years: draft['experience']=int(years.group(1))
    for location in locations:
        if location.casefold() in text.casefold(): draft['location']=location; break
    first=next((x.strip() for x in text.splitlines() if x.strip()),'')
    if 2<=len(first.split())<=5 and len(first)<80 and not re.search(r'cv|resume|curriculum|@',first,re.I): draft['name']=first
    return Response({'draft':draft,'notice':'Review every suggestion. This rules-based parser can miss or misclassify information. Nothing has been saved.'})


@api_view(['GET','POST'])
def opportunities(request):
    if request.method=='POST':
        require_role(request.user,'employer')
        obj=getattr(request.user,'business',None)
        if not obj or obj.status!='approved': return error('Your business must be approved before publishing.',403)
        serializer=OpportunitySerializer(data=request.data); serializer.is_valid(raise_exception=True)
        serializer.save(business=obj)
        return Response(serializer.data,status=201)
    qs=Opportunity.objects.select_related('business').order_by('-created_at')
    profile=request.user.profile
    if profile.role=='employer': qs=qs.filter(business__owner=request.user)
    else: qs=qs.filter(status='open',business__status='approved',business__owner__is_active=True)
    data=[]
    for obj in qs:
        item=OpportunitySerializer(obj).data
        if profile.role=='worker':
            item['match']=match(profile,obj)
            item['interested']=Interest.objects.filter(worker=request.user,opportunity=obj).exists()
        data.append(item)
    return Response(data)


@api_view(['GET','PATCH'])
def opportunity_detail(request,pk):
    obj=get_object_or_404(Opportunity,pk=pk)
    if request.method=='PATCH':
        if obj.business.owner_id!=request.user.id: return error('You cannot edit this opportunity.',403)
        serializer=OpportunitySerializer(obj,data=request.data,partial=True);serializer.is_valid(raise_exception=True);serializer.save()
        return Response(serializer.data)
    if obj.business.owner_id!=request.user.id and (obj.status!='open' or obj.business.status!='approved' or not obj.business.owner.is_active): return error('This opportunity is not available.',404)
    return Response(OpportunitySerializer(obj).data)


@api_view(['GET'])
def candidates(request,pk):
    obj=get_object_or_404(Opportunity,pk=pk,business__owner=request.user)
    data=[]
    for p in Profile.objects.filter(role='worker',published=True,user__is_active=True).select_related('user'):
        item=ProfileSerializer(p).data
        item['match']=match(p,obj)
        interest=Interest.objects.filter(worker=p.user,opportunity=obj).first()
        item['interested']=bool(interest)
        item['interest_message']=interest.message if interest else ''
        item['shortlisted']=Shortlist.objects.filter(worker=p.user,opportunity=obj).exists()
        today=timezone.localdate()
        item['credentials']=[{'kind':d.kind,'profession':d.profession,'skill':d.skill,'status':d.status,'expires':d.expires} for d in Document.objects.filter(owner=p.user,kind__in=['certificate','clearance'],status='verified') if d.expires is None or d.expires>=today]
        data.append(item)
    data.sort(key=lambda x:(x['match']['eligible'],x['match']['score'],len(x['match']['preferred_skills'])),reverse=True)
    return Response(data)


@api_view(['POST','DELETE'])
def express_interest(request,pk):
    require_role(request.user,'worker')
    obj=get_object_or_404(Opportunity,pk=pk,status='open',business__status='approved',business__owner__is_active=True)
    if request.method=='DELETE':
        Interest.objects.filter(worker=request.user,opportunity=obj).delete(); return Response({'detail':'Interest withdrawn.'})
    if not request.user.profile.published: return error('Complete and publish your profile before expressing interest.')
    if request.data.get('confirm_availability') is not True: return error('Confirm your availability before expressing interest.')
    interest,_=Interest.objects.update_or_create(worker=request.user,opportunity=obj,defaults={'message':str(request.data.get('message',''))[:2000]})
    return Response({'id':interest.id,'detail':'Your interest has been shared with the employer.'})


@api_view(['POST','DELETE'])
def shortlist(request,pk,worker_id):
    obj=get_object_or_404(Opportunity,pk=pk,business__owner=request.user)
    worker=get_object_or_404(User,pk=worker_id,is_active=True,profile__role='worker',profile__published=True)
    if request.method=='DELETE': Shortlist.objects.filter(worker=worker,opportunity=obj).delete()
    else: Shortlist.objects.get_or_create(worker=worker,opportunity=obj)
    return Response({'detail':'Shortlist updated.'})


@api_view(['GET','POST'])
def engagements(request):
    if request.method=='POST':
        require_role(request.user,'employer')
        obj=get_object_or_404(Opportunity,pk=request.data.get('opportunity'),business__owner=request.user,status='open')
        if obj.business.status!='approved': return error('Business approval is required.',403)
        worker=get_object_or_404(User,pk=request.data.get('worker'),is_active=True,profile__role='worker',profile__published=True)
        if Engagement.objects.filter(worker=worker,opportunity=obj).exists(): return error('An offer already exists for this worker and gig.')
        if not match(worker.profile,obj)['eligible']: return error('This worker does not meet the current essential requirements.')
        eng=Engagement.objects.create(worker=worker,opportunity=obj,work_type=obj.work_type,agreed_amount=obj.budget,agreed_deliverables=obj.deliverables,agreed_start=obj.start_date,agreed_end=obj.end_date)
        return Response(EngagementSerializer(eng,context={'request':request}).data,status=201)
    qs=Engagement.objects.filter(Q(worker=request.user)|Q(opportunity__business__owner=request.user)).select_related('worker__profile','opportunity__business').order_by('-created_at')
    return Response(EngagementSerializer(qs,many=True,context={'request':request}).data)


@api_view(['POST'])
def engagement_action(request,pk,action):
    # Row locking serializes funding, approval, and payout transitions.
    with transaction.atomic():
        eng=get_object_or_404(Engagement.objects.select_for_update(),pk=pk)
        employer=eng.opportunity.business.owner_id==request.user.id
        worker=eng.worker_id==request.user.id
        if not employer and not worker: return error('This engagement is private.',403)
        transitions={'accept':('offered','accepted',worker),'submit':('funded','submitted',worker),'approve':('submitted','approved',employer),'request-changes':('submitted','funded',employer),'cancel':('offered','cancelled',employer or worker)}
        if action=='dispute':
            if eng.status not in ['funded','submitted','approved']: return error('This engagement cannot be disputed at this stage.')
            if not str(request.data.get('note','')).strip(): return error('Explain the issue for admin review.')
            eng.status='disputed';eng.note=str(request.data['note'])[:3000]
        elif action in ['fund-demo','payout-demo']:
            if not settings.DEMO_PAYMENTS: return error('Demo payment actions are disabled.',403)
            if not employer: return error('Only the employer can perform this action.',403)
            if eng.work_type!='gig': return error('Platform payment processing currently applies to gigs only.')
            expected='accepted' if action=='fund-demo' else 'approved'
            if eng.status!=expected: return error('This payment action is not available at the current stage.')
            if action=='payout-demo' and eng.payment_mode!='demo': return error('Sandbox collections cannot be paid out through a demo action.')
            eng.status='funded' if action=='fund-demo' else 'completed';eng.payment_mode='demo'
            Payment.objects.create(engagement=eng,reference='DEMO-'+uuid.uuid4().hex,amount=eng.agreed_amount,status='collection_simulated' if action=='fund-demo' else 'payout_simulated',mode='demo')
        elif action in transitions:
            expected,target,allowed=transitions[action]
            if not allowed:return error('This action belongs to the other participant.',403)
            if eng.status!=expected:return error('This action is not available at the current stage.')
            if action=='accept':
                # Serialize acceptances for one worker, including offers from different businesses.
                User.objects.select_for_update().get(pk=eng.worker_id)
                if Engagement.objects.filter(worker=eng.worker,status__in=['accepted','funded','submitted','approved'],agreed_start__lte=eng.agreed_end,agreed_end__gte=eng.agreed_start).exclude(pk=eng.pk).exists():
                    return error('These dates overlap an accepted engagement.')
                if eng.work_type!='gig':target='hired'
            if action=='submit':
                if not str(request.data.get('submission','')).strip(): return error('Describe the work you are submitting, with any delivery links.')
                eng.submission=str(request.data['submission'])[:5000]
                links=request.data.get('links',[]);ids=request.data.get('attachment_ids',[])
                if not isinstance(links,list) or len(links)>10:return error('Add up to 10 delivery links.')
                from urllib.parse import urlsplit
                for link in links:
                    if not isinstance(link,str):return error('Delivery links must be web addresses.')
                    serializers.URLField().run_validation(link)
                    if urlsplit(link).scheme not in ['http','https']:return error('Delivery links must start with https:// or http://.')
                if not isinstance(ids,list) or len(ids)>10 or any(type(pk) is not int for pk in ids) or len(ids)!=len(set(ids)):return error('Attach up to 10 unique files.')
                attachments=SubmissionAttachment.objects.filter(pk__in=ids,engagement=eng,uploader=request.user,submission__isnull=True)
                if attachments.count()!=len(ids):return error('Only your own draft files for this gig can be submitted.')
                submission=WorkSubmission.objects.create(engagement=eng,notes=eng.submission,links=links)
                attachments.update(submission=submission)
            if action=='request-changes' and not str(request.data.get('note','')).strip():return error('Describe the changes you need.')
            eng.status=target;eng.note=str(request.data.get('note',''))[:3000]
        else:return error('Unknown action.',404)
        eng.save()
    return Response(EngagementSerializer(eng,context={'request':request}).data)


@api_view(['POST'])
def review(request,pk):
    eng=get_object_or_404(Engagement,pk=pk,status='completed')
    if request.user.id not in [eng.worker_id,eng.opportunity.business.owner_id]:return error('Only participants can review this gig.',403)
    if Review.objects.filter(engagement=eng,author=request.user).exists():return error('You have already reviewed this engagement.')
    serializer=ReviewSerializer(data=request.data);serializer.is_valid(raise_exception=True)
    serializer.save(engagement=eng,author=request.user)
    return Response({'detail':'Review saved. Reviews become visible to both participants once both submit.'},status=201)


@api_view(['POST'])
def checkout(request,pk):
    eng=get_object_or_404(Engagement,pk=pk,opportunity__business__owner=request.user,status='accepted')
    if eng.work_type!='gig':return error('Platform payments apply to gigs only.')
    key=settings.FLUTTERWAVE_SECRET_KEY
    if not key:return error('Flutterwave sandbox is not configured. Set FLUTTERWAVE_SECRET_KEY on the server.',503)
    if not key.startswith('FLWSECK_TEST'):return error('Only Flutterwave test keys are accepted by this prototype.',503)
    reference='FLIP-'+uuid.uuid4().hex
    payment=Payment.objects.create(engagement=eng,reference=reference,amount=eng.agreed_amount,mode='sandbox')
    try:
        response=requests.post('https://api.flutterwave.com/v3/payments',headers={'Authorization':'Bearer '+key},json={
            'tx_ref':reference,'amount':str(eng.agreed_amount),'currency':'UGX',
            'redirect_url':settings.FRONTEND_URL+'/?payment=return',
            'customer':{'email':request.user.email,'name':request.user.profile.name},
            'customizations':{'title':'FLIP Africa Sandbox','description':eng.opportunity.title}},timeout=20)
        payload=response.json()
        if response.ok and payload.get('status')=='success':return Response({'url':payload['data']['link'],'reference':reference})
    except (requests.RequestException,ValueError,KeyError):pass
    payment.status='failed';payment.save()
    return error('Could not start sandbox checkout. Retry or check your Flutterwave account configuration.',502)


@api_view(['POST'])
def verify_payment(request):
    reference=str(request.data.get('reference',''))
    transaction_id=str(request.data.get('transaction_id',''))
    payment=get_object_or_404(Payment,reference=reference,engagement__opportunity__business__owner=request.user,mode='sandbox')
    if payment.status=='verified':return Response({'detail':'Payment already verified.'})
    if not transaction_id.isdigit():return error('A valid transaction ID is required.')
    try:
        response=requests.get(f'https://api.flutterwave.com/v3/transactions/{transaction_id}/verify',headers={'Authorization':'Bearer '+settings.FLUTTERWAVE_SECRET_KEY},timeout=20)
        payload=response.json();data=payload.get('data',{})
        valid=response.ok and data.get('status')=='successful' and data.get('tx_ref')==reference and data.get('currency')=='UGX' and Decimal(str(data.get('amount',0)))==payment.amount
    except (requests.RequestException,ValueError,ArithmeticError):return error('Could not verify payment. Please retry.',502)
    if not valid:return error('Payment verification failed. Status, reference, currency and amount must match.')
    with transaction.atomic():
        eng=Engagement.objects.select_for_update().get(pk=payment.engagement_id)
        payment=Payment.objects.select_for_update().get(pk=payment.pk)
        if eng.status!='accepted' and payment.status!='verified':return error('The agreement changed. Contact admin to reconcile this payment.',409)
        payment.status='verified';payment.provider_id=transaction_id;payment.save()
        eng.status='funded';eng.payment_mode='sandbox';eng.save()
    return Response({'detail':'Sandbox collection verified. This does not establish escrow or trigger a payout.'})


@api_view(['GET','POST'])
def payout_account(request):
    require_role(request.user,'worker')
    obj=PayoutAccount.objects.filter(owner=request.user).first()
    if request.method=='POST':
        name=str(request.data.get('beneficiary_name','')).strip()
        network=request.data.get('network')
        number=str(request.data.get('number','')).strip().replace('+','').replace(' ','')
        if not name or len(name)>120 or network not in ['MTN','Airtel'] or not re.fullmatch(r'256\d{9}',number):
            return error('Enter a beneficiary name, MTN or Airtel, and a number in the format 256XXXXXXXXX. Use test details only.')
        obj,_=PayoutAccount.objects.update_or_create(owner=request.user,defaults={'beneficiary_name':name,'network':network,'number':number})
    return Response({'beneficiary_name':obj.beneficiary_name,'network':obj.network,'number':obj.number} if obj else None)


@api_view(['POST'])
def sandbox_payout(request,pk):
    key=settings.FLUTTERWAVE_SECRET_KEY
    if not key.startswith('FLWSECK_TEST'):return error('A Flutterwave v3 test secret key is required.',503)
    with transaction.atomic():
        eng=get_object_or_404(Engagement.objects.select_for_update(),pk=pk,opportunity__business__owner=request.user,status='approved',payment_mode='sandbox')
        if not eng.payments.filter(mode='sandbox',status='verified').exists():return error('A verified sandbox collection is required.')
        destination=PayoutAccount.objects.filter(owner=eng.worker).first()
        if not destination:return error('The worker must add their sandbox payout details in My gigs.')
        # A reserved record survives ambiguous timeouts. Never retry a transfer blindly.
        if eng.payments.filter(mode='sandbox_payout').exists():return error('A payout request already exists. Refresh its status or ask admin to reconcile it.')
        payment=Payment.objects.create(engagement=eng,reference='FLIP-PAYOUT-'+uuid.uuid4().hex,amount=eng.agreed_amount,mode='sandbox_payout',status='initiating')
    try:
        response=requests.post('https://api.flutterwave.com/v3/transfers',headers={'Authorization':'Bearer '+key},json={
            'reference':payment.reference,'amount':str(payment.amount),'currency':'UGX','debit_currency':'UGX',
            'account_bank':destination.network,'account_number':destination.number,'beneficiary_name':destination.beneficiary_name,
            'narration':'FLIP fictional gig sandbox payout'},timeout=20)
        payload=response.json();data=payload.get('data',{})
        if response.ok and payload.get('status')=='success' and data.get('id'):
            payment.provider_id=str(data['id']);payment.status='payout_pending';payment.save()
            return Response({'detail':'Sandbox transfer initiated. Refresh payout status to verify completion.'})
        payment.status='payout_rejected';payment.save()
    except (requests.RequestException,ValueError):
        payment.status='reconcile_required';payment.save()
        return error('The payout response is uncertain. Admin must reconcile the reference before any retry.',502)
    return error('The sandbox transfer was rejected. Check account transfer permissions and test wallet balance.',502)


@api_view(['POST'])
def verify_payout(request,pk):
    eng=get_object_or_404(Engagement,pk=pk)
    if request.user.id not in [eng.worker_id,eng.opportunity.business.owner_id]:return error('This engagement is private.',403)
    payment=get_object_or_404(Payment,engagement=eng,mode='sandbox_payout')
    if not payment.provider_id:return error('No provider transfer ID is available. Ask admin to reconcile the reference.')
    try:
        response=requests.get(f'https://api.flutterwave.com/v3/transfers/{payment.provider_id}',headers={'Authorization':'Bearer '+settings.FLUTTERWAVE_SECRET_KEY},timeout=20)
        payload=response.json();data=payload.get('data',{})
        if not response.ok or payload.get('status')!='success':return error('Could not retrieve the transfer status.',502)
        if data.get('reference')!=payment.reference or data.get('currency')!='UGX' or Decimal(str(data.get('amount',0)))!=payment.amount:return error('Transfer details do not match the agreement.',409)
    except (requests.RequestException,ValueError,ArithmeticError):return error('Could not check the sandbox transfer. Please retry.',502)
    with transaction.atomic():
        eng=Engagement.objects.select_for_update().get(pk=eng.pk)
        if str(data.get('status','')).upper()=='SUCCESSFUL':
            payment.status='payout_verified'
            # Disputed engagements stay frozen for administrator review.
            if eng.status=='approved':eng.status='completed';eng.save()
        elif str(data.get('status','')).upper()=='FAILED':payment.status='payout_failed'
        else:payment.status='payout_pending'
        payment.save()
    return Response({'detail':label_status(payment.status)})


def label_status(value):return value.replace('_',' ').capitalize()+'.'


@api_view(['POST'])
def upload_project_image(request):
    require_role(request.user,'worker')
    uploaded=request.FILES.get('file')
    if not uploaded:return error('Choose a project image.')
    if uploaded.size>5*1024*1024:return error('Project images must be 5 MB or smaller.')
    from PIL import Image, ImageOps, UnidentifiedImageError
    from io import BytesIO
    from django.core.files.base import ContentFile
    try:
        with Image.open(uploaded) as image:
            if image.format not in ['PNG','JPEG','WEBP']:return error('Choose a JPG, PNG or WebP image.')
            if image.width*image.height>20000000:return error('Choose an image smaller than 20 megapixels.')
            image=ImageOps.exif_transpose(image)
            image.thumbnail((2000,2000))
            output=BytesIO()
            image.convert('RGB').save(output,format='JPEG',quality=88)
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
        return error('This file is not a readable image.')
    obj=ProjectImage(owner=request.user)
    obj.file.save(uuid.uuid4().hex+'.jpg',ContentFile(output.getvalue()))
    return Response({'id':obj.id},status=201)


@api_view(['GET'])
@permission_classes([AllowAny])
def project_image(request,pk):
    obj=get_object_or_404(ProjectImage.objects.select_related('owner__profile'),pk=pk)
    profile=obj.owner.profile
    attached=any(pk in p.get('image_ids',[]) for p in profile.projects)
    if not (request.user.is_authenticated and (request.user.id==obj.owner_id or request.user.is_staff)) and not (profile.published and obj.owner.is_active and attached):
        return error('This project image is not published.',403)
    response=FileResponse(obj.file.open('rb'),content_type='image/jpeg')
    response['X-Content-Type-Options']='nosniff'
    response['Cache-Control']='private, no-store'
    return response


def connection_data(obj,request):
    opp=obj.opportunity
    profile=obj.worker.profile
    candidate=ProfileSerializer(profile).data
    interest=Interest.objects.filter(worker=obj.worker,opportunity=opp).first()
    candidate.update(match=match(profile,opp),interested=bool(interest),interest_message=interest.message if interest else '',shortlisted=Shortlist.objects.filter(worker=obj.worker,opportunity=opp).exists())
    candidate['credentials']=[{'kind':d.kind,'profession':d.profession,'skill':d.skill,'status':d.status,'expires':d.expires} for d in Document.objects.filter(owner=obj.worker,kind__in=['certificate','clearance'],status='verified') if d.expires is None or d.expires>=timezone.localdate()]
    opportunity=OpportunitySerializer(opp).data
    opportunity.update(interested=bool(interest),match=candidate['match'])
    return {'id':obj.id,'opportunity':opportunity,'candidate':candidate,'message':interest.message if interest else '','created_at':obj.created_at}


@api_view(['GET'])
def interests(request):
    qs=Interest.objects.select_related('opportunity__business','worker__profile').order_by('-created_at')
    if request.user.profile.role=='employer':qs=qs.filter(opportunity__business__owner=request.user)
    else:qs=qs.filter(worker=request.user)
    return Response([connection_data(obj,request) for obj in qs])


@api_view(['GET'])
def shortlists(request):
    require_role(request.user,'employer')
    qs=Shortlist.objects.filter(opportunity__business__owner=request.user).select_related('opportunity__business','worker__profile').order_by('-created_at')
    return Response([connection_data(obj,request) for obj in qs])


@api_view(['GET'])
def notifications(request):
    qs=Notification.objects.filter(user=request.user)
    unread=qs.filter(read_at__isnull=True).count()
    before=request.query_params.get('before')
    if before:
        if not before.isdigit():return error('Use a valid notification cursor.')
        qs=qs.filter(id__lt=int(before))
    items=list(qs.order_by('-id')[:51])
    return Response({'items':NotificationSerializer(items[:50],many=True).data,'unread_count':unread,'next_before':items[49].id if len(items)>50 else None})


@api_view(['PATCH'])
def notification_read(request,pk):
    obj=get_object_or_404(Notification,pk=pk,user=request.user)
    value=request.data.get('read',True)
    if type(value) is not bool:return error('Read must be true or false.')
    obj.read_at=timezone.now() if value else None;obj.save(update_fields=['read_at'])
    return Response(NotificationSerializer(obj).data)


@api_view(['POST'])
def notifications_read_all(request):
    count=Notification.objects.filter(user=request.user,read_at__isnull=True).update(read_at=timezone.now())
    return Response({'updated':count})


@api_view(['GET','PATCH'])
def notification_preferences(request):
    obj,_=NotificationPreference.objects.get_or_create(user=request.user)
    if request.method=='PATCH':
        serializer=NotificationPreferenceSerializer(obj,data=request.data,partial=True);serializer.is_valid(raise_exception=True);serializer.save()
    from .email_service import configured
    return Response({'preferences':NotificationPreferenceSerializer(obj).data,'email_configured':configured(),'email_address':request.user.email})


@api_view(['POST'])
def notification_test_email(request):
    from .email_service import configured,safe_recipient
    if not configured():return error('Add your Gmail address and app password to .env, then restart the server and notification worker.',503)
    if not safe_recipient(request.user.email):return error('Demo addresses cannot receive email. Sign in with your own real email address to test.')
    from .notifications import notify
    pref,_=NotificationPreference.objects.get_or_create(user=request.user)
    if not pref.email_enabled or not pref.activity_alerts:return error('Enable email and account activity notifications before sending a test.')
    # Never accept an arbitrary destination from the request.
    notify(request.user,'system','Your Gig House email is connected','This is your requested test notification. Opportunity and account alerts will also appear in your notification centre.',{'page':'notifications'},'test-email:'+uuid.uuid4().hex)
    return Response({'detail':'Test email queued for your signed-in account. Provider acceptance appears in the admin email outbox.'},status=202)
