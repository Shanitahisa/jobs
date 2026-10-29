import io
import tempfile
from pathlib import Path
from PIL import Image
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from .tests import MarketplaceFlowTests
from .models import Opportunity, Engagement, Payment, Document, AdminAudit


class WorkspaceTests(TestCase):
    def setUp(self):
        MarketplaceFlowTests.setUp(self)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.media=override_settings(MEDIA_ROOT=self.tmp.name)
        self.media.enable();self.addCleanup(self.media.disable)
        self.admin=User.objects.create_user('admin@test.demo',is_staff=True)
        self.a=APIClient();self.a.force_authenticate(self.admin)
        self.opp=Opportunity.objects.create(business=self.business,**self.payload)
        self.eng=Engagement.objects.create(worker=self.worker,opportunity=self.opp,status='funded',agreed_amount=250000,agreed_deliverables='Photos',agreed_start=self.opp.start_date,agreed_end=self.opp.end_date)

    def file_status(self,client,url):
        response=client.get(url)
        if response.streaming:
            b''.join(response.streaming_content)
        return response.status_code

    def test_public_profile_privacy_and_unpublishing(self):
        p=self.worker.profile
        self.assertTrue(p.page_slug)
        url=f'/api/profiles/public/{p.page_slug}/'
        client=APIClient();r=client.get(url)
        self.assertEqual(r.status_code,200)
        self.assertNotIn('email',r.data);self.assertNotIn('user',r.data);self.assertNotIn('documents',r.data)
        p.published=False;p.save()
        self.assertEqual(client.get(url).status_code,404)
        p.published=True;p.save();self.worker.is_active=False;self.worker.save()
        self.assertEqual(client.get(url).status_code,404)

    def test_photo_validation_and_public_access(self):
        self.assertEqual(self.w.post('/api/me/photo/',{'file':SimpleUploadedFile('bad.jpg',b'bad')},format='multipart').status_code,400)
        buf=io.BytesIO();Image.new('RGB',(20,20),'white').save(buf,format='PNG')
        r=self.w.post('/api/me/photo/',{'file':SimpleUploadedFile('face.png',buf.getvalue(),content_type='image/png')},format='multipart')
        self.assertEqual(r.status_code,200,r.data)
        url=f'/api/profiles/{self.worker.id}/photo/'
        self.assertEqual(self.file_status(APIClient(),url),200)
        p=self.worker.profile;p.refresh_from_db();p.published=False;p.save()
        self.assertEqual(APIClient().get(url).status_code,404)
        self.assertEqual(self.w.delete('/api/me/photo/').status_code,200)

    def test_delivery_files_links_and_private_revision_history(self):
        url=f'/api/engagements/{self.eng.id}/attachments/'
        r=self.w.post(url,{'file':SimpleUploadedFile('report.txt',b'Completed project notes',content_type='text/plain')},format='multipart')
        self.assertEqual(r.status_code,201,r.data);fid=r.data['id']
        file_url=f'/api/submission-attachments/{fid}/'
        self.assertEqual(self.e.get(url).data,[])
        self.assertEqual(self.e.get(file_url).status_code,403)
        self.assertEqual(self.o.get(file_url).status_code,403)
        submit=f'/api/engagements/{self.eng.id}/submit/'
        self.assertEqual(self.w.post(submit,{'submission':'Ready','links':['javascript:alert(1)'],'attachment_ids':[fid]},format='json').status_code,400)
        r=self.w.post(submit,{'submission':'Ready for review','links':['https://example.com/work'],'attachment_ids':[fid]},format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(self.file_status(self.e,file_url),200)
        self.assertEqual(self.w.delete(file_url).status_code,403)
        history=self.e.get('/api/engagements/').data[0]['submissions']
        self.assertEqual(history[0]['links'],['https://example.com/work'])
        self.assertEqual(history[0]['attachments'][0]['name'],'report.txt')
        self.assertEqual(self.o.get(url).status_code,403)

    def test_payments_are_scoped_and_admin_can_inspect(self):
        Payment.objects.create(engagement=self.eng,reference='workspace-test',amount=250000,mode='demo')
        self.assertEqual(len(self.w.get('/api/payments/').data),1)
        self.assertEqual(len(self.e.get('/api/payments/').data),1)
        self.assertEqual(self.o.get('/api/payments/').data,[])
        self.assertEqual(len(self.a.get('/api/system/payments/').data),1)
        self.assertEqual(self.a.post('/api/system/payments/',{},format='json').status_code,405)

    def test_admin_permissions_suspension_and_audit(self):
        for section in ['overview','businesses','documents','users','opportunities','engagements','payments','emails','audit']:
            self.assertEqual(self.w.get(f'/api/system/{section}/').status_code,403,section)
            self.assertEqual(self.a.get(f'/api/system/{section}/').status_code,200,section)
        Token.objects.create(user=self.worker)
        r=self.a.post(f'/api/system/users/{self.worker.id}/',{'active':False,'note':'Account review'},format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertFalse(Token.objects.filter(user=self.worker).exists())
        self.assertEqual(AdminAudit.objects.get().action,'user_suspended')
        self.assertEqual(self.a.post(f'/api/system/users/{self.admin.id}/',{'active':False,'note':'Test'},format='json').status_code,403)
        self.assertEqual(self.w.post(f'/api/system/users/{self.employer.id}/',{'active':False,'note':'Test'},format='json').status_code,403)

    def test_business_review_requires_documents_and_records_decision(self):
        self.business.status='pending';self.business.save()
        url=f'/api/system/businesses/{self.business.id}/'
        self.assertEqual(self.a.post(url,{'status':'approved'},format='json').status_code,400)
        for kind in ['registration','licence']:
            Document.objects.create(owner=self.employer,kind=kind,title=kind,file='unused.pdf')
        r=self.a.post(url,{'status':'approved'},format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertTrue(AdminAudit.objects.filter(action='business_review').exists())

    def test_dispute_resolution_cannot_invent_funding(self):
        self.eng.status='disputed';self.eng.save()
        url=f'/api/system/engagements/{self.eng.id}/'
        self.assertEqual(self.a.post(url,{'action':'resume_work','note':'Reviewed'},format='json').status_code,400)
        Payment.objects.create(engagement=self.eng,reference='funded-test',amount=250000,mode='demo',status='collection_simulated')
        self.assertEqual(self.a.post(url,{'action':'resume_work','note':'Reviewed'},format='json').status_code,200)
        self.eng.refresh_from_db();self.assertEqual(self.eng.status,'funded')
        self.assertEqual(self.eng.payments.count(),1)

    def test_registration_queues_one_welcome_and_rejects_case_variants(self):
        from .models import Notification,EmailDelivery
        client=APIClient()
        payload={'name':'New Member','role':'worker','email':'New.Member@unit.example','password':'StrongPass!2026','confirm_password':'StrongPass!2026'}
        with self.captureOnCommitCallbacks(execute=True):
            r=client.post('/api/auth/register/',payload,format='json')
        self.assertEqual(r.status_code,201,r.data)
        user=User.objects.get(pk=r.data['user']['id'])
        self.assertEqual(user.email,'new.member@unit.example')
        self.assertEqual(Notification.objects.filter(user=user,event_key=f'welcome:u{user.pk}').count(),1)
        self.assertEqual(EmailDelivery.objects.filter(notification__user=user).count(),1)
        payload['email']='NEW.MEMBER@UNIT.EXAMPLE'
        self.assertEqual(client.post('/api/auth/register/',payload,format='json').status_code,400)

    def test_database_enforces_case_insensitive_email_uniqueness(self):
        from django.db import transaction,IntegrityError
        with self.assertRaises(IntegrityError):
            with transaction.atomic():User.objects.create_user('different-username',email=self.worker.email.upper())

    def test_people_search_and_profile_privacy(self):
        self.assertEqual(APIClient().get('/api/people/').status_code,401)
        r=self.w.get('/api/people/?q=worker')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.data['items'][0]['id'],self.worker.id)
        self.assertNotIn('email',r.data['items'][0])
        detail=self.e.get(f'/api/people/{self.worker.id}/').data
        self.assertTrue(detail['professions']);self.assertNotIn('email',detail);self.assertNotIn('documents',detail)
        p=self.worker.profile;p.published=False;p.save()
        detail=self.e.get(f'/api/people/{self.worker.id}/').data
        self.assertNotIn('professions',detail);self.assertNotIn('projects',detail)
        self.worker.is_active=False;self.worker.save()
        self.assertEqual(self.e.get(f'/api/people/{self.worker.id}/').status_code,404)
        self.assertEqual(self.e.get('/api/people/?q=worker').data['items'],[])
