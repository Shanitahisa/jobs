from datetime import timedelta
from django.test import TestCase, override_settings
from unittest.mock import patch, Mock
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Profile,Business,Opportunity,Engagement,Document,Payment,PayoutAccount,ProjectImage


class MarketplaceFlowTests(TestCase):
    def setUp(self):
        self.employer=User.objects.create_user('employer@test.demo',email='employer@test.demo',password='FlipDemo!2026')
        Profile.objects.create(user=self.employer,name='Fictional Employer',role='employer')
        self.business=Business.objects.create(owner=self.employer,name='Fictional Studio',industry='Events',location='Kampala',registration_number='DEMO',status='approved')
        self.worker=User.objects.create_user('worker@test.demo',email='worker@test.demo',password='FlipDemo!2026')
        Profile.objects.create(user=self.worker,name='Fictional Worker',role='worker',headline='Photographer',location='Kampala',availability='weekends',experience=2,published=True,work_types=['gig'],professions=[{'category':'Creative & Media','profession':'Photographer','skills':['Event photography','Photo editing']}])
        self.other=User.objects.create_user('other@test.demo',password='FlipDemo!2026')
        Profile.objects.create(user=self.other,name='Other employer',role='employer')
        self.e=APIClient();self.e.force_authenticate(self.employer)
        self.w=APIClient();self.w.force_authenticate(self.worker)
        self.o=APIClient();self.o.force_authenticate(self.other)
        today=timezone.localdate()
        self.payload={'title':'Fictional photography gig','description':'Demo only','profession':'Photographer','skills':['Event photography','Photo editing'],'location':'Kampala','availability':'weekends','start_date':str(today+timedelta(days=2)),'end_date':str(today+timedelta(days=2)),'budget':'250000','deliverables':'40 edited photographs','work_type':'gig'}

    def test_full_journey_and_no_match(self):
        response=self.e.post('/api/opportunities/',self.payload,format='json');self.assertEqual(response.status_code,201,response.data)
        oid=response.data['id']
        matches=self.e.get(f'/api/opportunities/{oid}/candidates/').data
        self.assertTrue(matches[0]['match']['eligible']);self.assertTrue(matches[0]['match']['reasons'])
        response=self.w.post(f'/api/opportunities/{oid}/interest/',{'message':'Fictional interest','confirm_availability':True},format='json');self.assertEqual(response.status_code,200,response.data)
        response=self.e.post(f'/api/opportunities/{oid}/shortlist/{self.worker.id}/',{},format='json');self.assertEqual(response.status_code,200)
        matches=self.e.get(f'/api/opportunities/{oid}/candidates/').data
        self.assertTrue(matches[0]['interested']);self.assertTrue(matches[0]['shortlisted'])
        response=self.e.post('/api/engagements/',{'opportunity':oid,'worker':self.worker.id},format='json');self.assertEqual(response.status_code,201,response.data)
        gid=response.data['id']
        # Unrelated users cannot inspect private matches or perform gig actions.
        self.assertEqual(self.o.get(f'/api/opportunities/{oid}/candidates/').status_code,404)
        self.assertEqual(self.o.post(f'/api/engagements/{gid}/accept/',{},format='json').status_code,403)
        self.assertEqual(self.w.post(f'/api/engagements/{gid}/accept/',{},format='json').status_code,200)
        self.assertEqual(self.e.post(f'/api/engagements/{gid}/fund-demo/',{},format='json').status_code,200)
        # Repeated funding does not create a duplicate payment.
        self.assertEqual(self.e.post(f'/api/engagements/{gid}/fund-demo/',{},format='json').status_code,400)
        self.assertEqual(self.w.post(f'/api/engagements/{gid}/submit/',{'submission':'Fictional completed work'},format='json').status_code,200)
        self.assertEqual(self.e.post(f'/api/engagements/{gid}/approve/',{},format='json').status_code,200)
        self.assertEqual(self.e.post(f'/api/engagements/{gid}/payout-demo/',{},format='json').status_code,200)
        self.assertEqual(self.w.post(f'/api/engagements/{gid}/review/',{'rating':5,'comment':'Great fictional gig'},format='json').status_code,201)
        self.assertEqual(self.e.get('/api/engagements/').data[0]['reviews'],[])
        self.assertEqual(self.e.post(f'/api/engagements/{gid}/review/',{'rating':4,'comment':'Good fictional delivery'},format='json').status_code,201)
        self.assertEqual(len(self.e.get('/api/engagements/').data[0]['reviews']),2)
        response=self.e.patch(f'/api/opportunities/{oid}/',{'skills':['Event photography','Underwater photography']},format='json');self.assertEqual(response.status_code,200)
        result=self.e.get(f'/api/opportunities/{oid}/candidates/').data[0]['match']
        self.assertFalse(result['eligible']);self.assertIn('Underwater photography',result['missing_skills'])
        self.assertEqual(Engagement.objects.get(pk=gid).agreed_amount,250000)

    def test_validation_and_verification(self):
        self.assertEqual(self.e.post('/api/opportunities/',{},format='json').status_code,400)
        bad={**self.payload,'skills':[]};self.assertEqual(self.e.post('/api/opportunities/',bad,format='json').status_code,400)
        self.assertEqual(self.w.patch('/api/me/',{'location':''},format='json').status_code,400)
        self.business.status='pending';self.business.save()
        self.assertEqual(self.e.post('/api/opportunities/',self.payload,format='json').status_code,403)

    def test_private_upload_and_cv_draft(self):
        cv=SimpleUploadedFile('cv.txt',b'Fictional Name\nKampala\n3 years experience in Event photography and Photo editing',content_type='text/plain')
        response=self.w.post('/api/documents/',{'kind':'cv','title':'Demo CV','file':cv},format='multipart');self.assertEqual(response.status_code,201,response.data)
        did=response.data['id']
        self.assertEqual(self.e.get(f'/api/documents/{did}/download/').status_code,403)
        response=self.w.post(f'/api/documents/{did}/parse/',{},format='json');self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['draft']['location'],'Kampala');self.assertEqual(response.data['draft']['experience'],3)
        self.worker.profile.refresh_from_db();self.assertEqual(self.worker.profile.experience,2)

    def test_registration_and_login(self):
        client=APIClient()
        data={'name':'New Fictional Worker','email':'new@test.demo','password':'AnotherStrong!2026','confirm_password':'AnotherStrong!2026','role':'worker'}
        response=client.post('/api/auth/register/',data,format='json');self.assertEqual(response.status_code,201,response.data)
        self.assertIn('token',response.data)
        self.assertEqual(client.post('/api/auth/login/',{'email':data['email'],'password':data['password']},format='json').status_code,200)
        self.assertEqual(client.get('/api/opportunities/').status_code,401)

    @override_settings(FLUTTERWAVE_SECRET_KEY='FLWSECK_TEST-fictional')
    @patch('marketplace.views.requests.get')
    @patch('marketplace.views.requests.post')
    def test_sandbox_collection_and_payout(self,post,get):
        opp=Opportunity.objects.create(business=self.business,**self.payload)
        eng=Engagement.objects.create(worker=self.worker,opportunity=opp,status='accepted',agreed_amount=250000,agreed_deliverables='40 photos',agreed_start=opp.start_date,agreed_end=opp.end_date)
        payment=Payment.objects.create(engagement=eng,reference='TEST-collection',amount=250000,mode='sandbox')
        get.return_value=Mock(ok=True,json=lambda:{'data':{'status':'successful','tx_ref':payment.reference,'currency':'UGX','amount':249999}})
        self.assertEqual(self.e.post('/api/payments/verify/',{'reference':payment.reference,'transaction_id':'123'},format='json').status_code,400)
        get.return_value=Mock(ok=True,json=lambda:{'data':{'status':'successful','tx_ref':payment.reference,'currency':'UGX','amount':250000}})
        self.assertEqual(self.e.post('/api/payments/verify/',{'reference':payment.reference,'transaction_id':'123'},format='json').status_code,200)
        eng.refresh_from_db();self.assertEqual(eng.status,'funded')
        eng.status='approved';eng.save()
        PayoutAccount.objects.create(owner=self.worker,beneficiary_name='Fictional Name',network='MTN',number='256700000001')
        post.return_value=Mock(ok=True,json=lambda:{'status':'success','data':{'id':456}})
        self.assertEqual(self.e.post(f'/api/engagements/{eng.id}/sandbox-payout/',{},format='json').status_code,200)
        self.assertEqual(self.e.post(f'/api/engagements/{eng.id}/sandbox-payout/',{},format='json').status_code,400)
        transfer=Payment.objects.get(engagement=eng,mode='sandbox_payout')
        get.return_value=Mock(ok=True,json=lambda:{'status':'success','data':{'status':'SUCCESSFUL','reference':transfer.reference,'currency':'UGX','amount':250000}})
        self.assertEqual(self.w.post(f'/api/engagements/{eng.id}/verify-payout/',{},format='json').status_code,200)
        eng.refresh_from_db();self.assertEqual(eng.status,'completed')

    def test_profession_clearance_and_overlap(self):
        opp=Opportunity.objects.create(business=self.business,required_clearance=True,**self.payload)
        from .matching import match
        result=match(self.worker.profile,opp);self.assertFalse(result['eligible'])
        doc=Document.objects.create(owner=self.worker,kind='clearance',profession='Photographer',title='Fictional clearance',file='test.txt',status='verified',expires=timezone.localdate()+timedelta(days=30))
        self.assertTrue(match(self.worker.profile,opp)['eligible'])
        doc.expires=timezone.localdate()-timedelta(days=1);doc.save()
        self.assertFalse(match(self.worker.profile,opp)['eligible'])

    def test_business_submission_and_admin_approval(self):
        self.assertEqual(self.e.post('/api/business/submit/',{},format='json').status_code,400)
        for kind in ['registration','licence']:
            file=SimpleUploadedFile(kind+'.txt',b'FICTIONAL DEMO DOCUMENT',content_type='text/plain')
            response=self.e.post('/api/documents/',{'kind':kind,'title':'Fictional '+kind,'file':file},format='multipart')
            self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(self.e.post('/api/business/submit/',{},format='json').status_code,200)
        self.business.refresh_from_db();self.assertEqual(self.business.status,'pending')
        self.e.patch('/api/business/',{'status':'approved'},format='json')
        self.business.refresh_from_db();self.assertNotEqual(self.business.status,'approved')
        from .admin import BusinessAdmin
        from django.contrib.admin.sites import site
        BusinessAdmin(Business,site).approve(None,Business.objects.filter(pk=self.business.pk))
        self.business.refresh_from_db();self.assertEqual(self.business.status,'approved')
        self.assertEqual(self.e.post('/api/opportunities/',self.payload,format='json').status_code,201)

    def test_non_gig_offer_confirms_hire_without_payroll(self):
        profile=self.worker.profile;profile.work_types=['part_time'];profile.save()
        payload={**self.payload,'work_type':'part_time'}
        opp=Opportunity.objects.create(business=self.business,**payload)
        response=self.e.post('/api/engagements/',{'opportunity':opp.id,'worker':self.worker.id},format='json')
        self.assertEqual(response.status_code,201,response.data)
        gid=response.data['id']
        response=self.w.post(f'/api/engagements/{gid}/accept/',{},format='json')
        self.assertEqual(response.status_code,200,response.data);self.assertEqual(response.data['status'],'hired')
        self.assertEqual(self.e.post(f'/api/engagements/{gid}/fund-demo/',{},format='json').status_code,400)

    def test_registration_confirmation_and_password_rules(self):
        client=APIClient()
        base={'name':'Fictional Person','email':'new@test.demo','role':'worker','password':'AnotherStrong!2026'}
        self.assertEqual(client.post('/api/auth/register/',base,format='json').status_code,400)
        self.assertEqual(client.post('/api/auth/register/',{**base,'confirm_password':'Different!2026'},format='json').status_code,400)
        for password in ['short','lowercase!2026','UPPERCASE!2026','NoNumbersHere!','NoSpecial2026','Has Spaces!2026','A'*129+'!1a','new@test.demoX1!']:
            response=client.post('/api/auth/register/',{**base,'password':password,'confirm_password':password},format='json')
            self.assertEqual(response.status_code,400,(password,response.data))
        self.assertFalse(User.objects.filter(username='new@test.demo').exists())

    def test_logout_revokes_each_role_and_session(self):
        from rest_framework.authtoken.models import Token
        self.other.is_staff=True;self.other.save()
        for user in [self.worker,self.employer,self.other]:
            client=APIClient();token=Token.objects.create(user=user)
            client.credentials(HTTP_AUTHORIZATION='Token '+token.key)
            self.assertEqual(client.get('/api/me/').status_code,200)
            self.assertEqual(client.post('/api/auth/logout/',{},format='json').status_code,200)
            self.assertFalse(Token.objects.filter(key=token.key).exists())
            self.assertEqual(client.get('/api/me/').status_code,401)
        client=APIClient();client.login(username=self.employer.username,password='FlipDemo!2026')
        self.assertEqual(client.get('/api/me/').status_code,200)
        self.assertEqual(client.post('/api/auth/logout/',{},format='json').status_code,200)
        self.assertNotIn('_auth_user_id',client.session)
        self.assertEqual(client.get('/api/me/').status_code,401)
        self.assertEqual(client.post('/api/auth/logout/',{},format='json').status_code,200)

    def test_project_image_upload_visibility_and_ownership(self):
        from PIL import Image
        from io import BytesIO
        image=BytesIO();Image.new('RGB',(12,12),'white').save(image,'PNG')
        response=self.w.post('/api/project-images/',{'file':SimpleUploadedFile('project.png',image.getvalue(),content_type='image/png')},format='multipart')
        self.assertEqual(response.status_code,201,response.data);iid=response.data['id']
        anonymous=APIClient()
        self.assertEqual(anonymous.get(f'/api/project-images/{iid}/').status_code,403)
        self.assertEqual(self.w.get(f'/api/project-images/{iid}/').status_code,200)
        project={'title':'Fictional portfolio','description':'A sample','url':'','image_ids':[iid]}
        self.assertEqual(self.o.patch('/api/me/',{'projects':[project]},format='json').status_code,400)
        self.assertEqual(self.w.patch('/api/me/',{'projects':[project]},format='json').status_code,200)
        self.assertEqual(anonymous.get(f'/api/project-images/{iid}/').status_code,200)
        response=self.w.post('/api/project-images/',{'file':SimpleUploadedFile('invalid.png',b'not an image')},format='multipart')
        self.assertEqual(response.status_code,400)

    def test_optional_skill_certificates_and_industry_categories(self):
        response=self.w.patch('/api/me/',{'professions':self.worker.profile.professions},format='json')
        self.assertEqual(response.status_code,200)
        self.assertFalse(Document.objects.filter(owner=self.worker).exists())
        doc=SimpleUploadedFile('certificate.txt',b'FICTIONAL SKILL CERTIFICATE',content_type='text/plain')
        response=self.w.post('/api/documents/',{'kind':'certificate','profession':'Photographer','skill':'Photo editing','title':'Optional certificate','file':doc},format='multipart')
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['skill'],'Photo editing')
        self.assertEqual(self.e.get(f"/api/documents/{response.data['id']}/download/").status_code,403)
        self.assertEqual(self.e.patch('/api/business/',{'industry':'Creative & Media'},format='json').status_code,200)
        self.assertEqual(self.e.patch('/api/business/',{'industry':'Not a listed category'},format='json').status_code,400)

    def test_interest_and_shortlist_lists_are_scoped_to_account(self):
        opp=Opportunity.objects.create(business=self.business,**self.payload)
        self.w.post(f'/api/opportunities/{opp.id}/interest/',{'message':'I can help with this gig','confirm_availability':True},format='json')
        self.e.post(f'/api/opportunities/{opp.id}/shortlist/{self.worker.id}/',{},format='json')
        employer=self.e.get('/api/interests/');worker=self.w.get('/api/interests/')
        self.assertEqual(len(employer.data),1);self.assertEqual(len(worker.data),1)
        self.assertEqual(employer.data[0]['message'],'I can help with this gig')
        self.assertEqual(employer.data[0]['opportunity']['id'],opp.id)
        self.assertTrue(employer.data[0]['candidate']['shortlisted'])
        self.assertEqual(len(self.e.get('/api/shortlists/').data),1)
        self.assertEqual(self.o.get('/api/interests/').data,[])
        self.assertEqual(self.o.get('/api/shortlists/').data,[])
        self.assertEqual(self.w.get('/api/shortlists/').status_code,403)
        opp.status='closed';opp.save()
        self.assertEqual(len(self.w.get('/api/interests/').data),1)
