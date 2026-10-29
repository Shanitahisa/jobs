from datetime import timedelta
from unittest.mock import Mock,patch
from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase,override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Profile,Business,Opportunity,Notification,NotificationPreference,EmailDelivery,Interest,Shortlist
from .notifications import notify
from .email_service import process_outbox


SMTP_TEST_SETTINGS={'EMAIL_NOTIFICATIONS_ENABLED':True,'GMAIL_SMTP_HOST':'smtp.gmail.com','GMAIL_SMTP_PORT':587,'GMAIL_SMTP_USER':'sender@gmail.com','GMAIL_SMTP_PASSWORD':'fake-app-password','GMAIL_SMTP_USE_TLS':True,'GMAIL_SMTP_USE_SSL':False,'GMAIL_SENDER_NAME':'Gig House','GMAIL_REPLY_TO_EMAIL':'','DEFAULT_FROM_EMAIL':'sender@gmail.com'}


class NotificationTests(TestCase):
    def setUp(self):
        self.employer=User.objects.create_user('owner@flip.demo',email='owner@flip.demo',password='FlipDemo!2026')
        Profile.objects.create(user=self.employer,name='Fictional Owner',role='employer')
        self.business=Business.objects.create(owner=self.employer,name='Fictional business',industry='Creative & Media',location='Kampala',registration_number='DEMO',status='approved')
        self.worker=User.objects.create_user('talent@flip.demo',email='talent@flip.demo',password='FlipDemo!2026')
        Profile.objects.create(user=self.worker,name='Fictional Talent',role='worker',published=True,headline='Photographer',location='Kampala',availability='weekends',experience=2,work_types=['gig'],professions=[{'category':'Creative & Media','profession':'Photographer','skills':['Photo editing','Photography']}])
        self.w=APIClient();self.w.force_authenticate(self.worker)
        self.e=APIClient();self.e.force_authenticate(self.employer)
        day=timezone.localdate()+timedelta(days=3)
        self.payload={'business':self.business,'title':'Fictional camera gig','description':'Demo','profession':'Photographer','skills':['Photography'],'location':'Kampala','availability':'weekends','start_date':day,'end_date':day,'budget':100000,'deliverables':'Photos','work_type':'gig'}

    def test_matching_events_are_committed_deduplicated_and_preference_aware(self):
        with self.captureOnCommitCallbacks(execute=True):opp=Opportunity.objects.create(**self.payload)
        notices=Notification.objects.filter(user=self.worker,category='opportunity')
        self.assertEqual(notices.count(),1)
        self.assertEqual(notices.get().target['opportunity_id'],opp.pk)
        with self.captureOnCommitCallbacks(execute=True):
            opp.skills=['Photography','Photo editing'];opp.save()
        self.assertEqual(notices.count(),1)
        pref=NotificationPreference.objects.get(user=self.worker);pref.opportunity_alerts=False;pref.save()
        with self.captureOnCommitCallbacks(execute=True):Opportunity.objects.create(**self.payload)
        self.assertEqual(notices.count(),1)
        pref.opportunity_alerts=True;pref.save()
        with self.captureOnCommitCallbacks(execute=True):Opportunity.objects.create(**{**self.payload,'skills':['Underwater photography']})
        self.assertEqual(notices.count(),1)
        before=Notification.objects.count()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValueError):
                with transaction.atomic():
                    Opportunity.objects.create(**self.payload)
                    raise ValueError('Rollback this fictional action')
        self.assertEqual(Notification.objects.count(),before)

    def test_interest_shortlist_and_notification_privacy(self):
        opp=Opportunity.objects.create(**self.payload)
        with self.captureOnCommitCallbacks(execute=True):Interest.objects.create(worker=self.worker,opportunity=opp)
        employer_notice=Notification.objects.get(user=self.employer)
        with self.captureOnCommitCallbacks(execute=True):Shortlist.objects.create(worker=self.worker,opportunity=opp)
        self.assertTrue(Notification.objects.filter(user=self.worker,title='You made the shortlist').exists())
        self.assertEqual(self.w.patch(f'/api/notifications/{employer_notice.pk}/',{'read':True},format='json').status_code,404)
        response=self.e.get('/api/notifications/');self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['unread_count'],1)
        self.assertEqual(response.data['items'][0]['id'],employer_notice.pk)
        self.e.patch(f'/api/notifications/{employer_notice.pk}/',{'read':True},format='json')
        self.assertEqual(self.e.get('/api/notifications/').data['unread_count'],0)
        self.e.patch(f'/api/notifications/{employer_notice.pk}/',{'read':False},format='json')
        self.e.post('/api/notifications/read-all/',{},format='json')
        self.assertEqual(self.e.get('/api/notifications/').data['unread_count'],0)
        self.assertEqual(self.w.get('/api/notifications/').data['unread_count'],1)

    def test_preferences_and_email_configuration_are_private(self):
        response=self.w.patch('/api/notifications/preferences/',{'email_enabled':False,'browser_alerts':True},format='json')
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.data['preferences']['email_enabled'])
        self.assertNotIn('GMAIL_SMTP_PASSWORD',str(response.data));self.assertNotIn('EMAIL_HOST_PASSWORD',str(response.data))
        self.assertTrue(self.e.get('/api/notifications/preferences/').data['preferences']['email_enabled'])

    def test_opportunity_changes_and_withdrawal_notify_the_other_side(self):
        opp=Opportunity.objects.create(**self.payload)
        interest=Interest.objects.create(worker=self.worker,opportunity=opp)
        with self.captureOnCommitCallbacks(execute=True):
            opp.status='closed';opp.save()
        self.assertTrue(Notification.objects.filter(user=self.worker,title='An opportunity you followed has closed').exists())
        with self.captureOnCommitCallbacks(execute=True):interest.delete()
        self.assertTrue(Notification.objects.filter(user=self.employer,title='An expression of interest was withdrawn').exists())

    @override_settings(**SMTP_TEST_SETTINGS)
    @patch('marketplace.email_service.smtplib.SMTP')
    def test_gmail_outbox_acceptance_and_no_duplicate_send(self,smtp):
        self.worker.email='worker@gighouse-test.ug';self.worker.save()
        notice=notify(self.worker,'activity','Fictional alert','This is a mocked unit test.',{'page':'gigs'},'unit-email')
        smtp.return_value.send_message.return_value={}
        result=process_outbox();self.assertEqual(result['accepted'],1)
        delivery=EmailDelivery.objects.get(notification=notice)
        self.assertEqual(delivery.status,'accepted');self.assertEqual(delivery.attempts,1)
        smtp.assert_called_once_with('smtp.gmail.com',587,timeout=12)
        smtp.return_value.starttls.assert_called_once()
        smtp.return_value.login.assert_called_once_with('sender@gmail.com','fake-app-password')
        message=smtp.return_value.send_message.call_args.args[0]
        self.assertEqual(message['To'],self.worker.email)
        self.assertIn('Open Gig House',message.get_body(preferencelist=('plain',)).get_content())
        self.assertEqual(delivery.provider_id,message['Message-ID'])
        self.assertEqual(process_outbox()['processed'],0);self.assertEqual(smtp.call_count,1)

    @override_settings(**SMTP_TEST_SETTINGS)
    @patch('marketplace.email_service.smtplib.SMTP')
    def test_demo_addresses_and_opt_out_never_reach_gmail(self,smtp):
        notify(self.worker,'activity','Fictional demo alert','No external send.',{},'demo-email')
        self.assertEqual(process_outbox()['accepted'],0)
        self.assertEqual(EmailDelivery.objects.get().status,'suppressed');smtp.assert_not_called()
        self.worker.email='worker@gighouse-test.ug';self.worker.save()
        notice=notify(self.worker,'activity','Another alert','Preference will change.',{},'optout-email')
        NotificationPreference.objects.filter(user=self.worker).update(email_enabled=False)
        process_outbox()
        self.assertEqual(EmailDelivery.objects.get(notification=notice).status,'suppressed');smtp.assert_not_called()

    @override_settings(**SMTP_TEST_SETTINGS)
    @patch('marketplace.email_service.smtplib.SMTP')
    def test_uncertain_email_is_not_blindly_retried(self,smtp):
        self.worker.email='worker@gighouse-test.ug';self.worker.save()
        notice=notify(self.worker,'activity','Mock timeout','No actual message is sent.',{},'timeout-email')
        smtp.return_value.send_message.side_effect=TimeoutError()
        process_outbox();self.assertEqual(EmailDelivery.objects.get(notification=notice).status,'uncertain')
        self.assertEqual(process_outbox()['processed'],0);self.assertEqual(smtp.call_count,1)

    @override_settings(EMAIL_NOTIFICATIONS_ENABLED=False)
    @patch('marketplace.email_service.smtplib.SMTP')
    def test_missing_configuration_keeps_email_queued(self,smtp):
        notice=notify(self.worker,'activity','A queued alert','No credentials required for in-app notifications.',{},'no-config')
        self.assertFalse(process_outbox()['configured'])
        self.assertEqual(EmailDelivery.objects.get(notification=notice).status,'queued');smtp.assert_not_called()

    @override_settings(**SMTP_TEST_SETTINGS)
    @override_settings(MAILERS={'default':{'BACKEND':'marketplace.email_backend.GmailSMTPEmailBackend'}})
    @patch('marketplace.email_service.smtplib.SMTP')
    def test_django_email_backend_uses_gmail(self,smtp):
        from django.core.mail import EmailMessage
        smtp.return_value.send_message.return_value={}
        self.assertEqual(EmailMessage(subject='Mock backend test',body='No external message is sent.',to=['worker@gighouse-test.ug']).send(),1)
        smtp.return_value.send_message.assert_called_once()

    @override_settings(**SMTP_TEST_SETTINGS)
    @patch('marketplace.email_service.smtplib.SMTP')
    def test_authentication_failure_is_reported_without_revealing_credentials(self,smtp):
        import smtplib
        self.worker.email='worker@gighouse-test.ug';self.worker.save()
        notice=notify(self.worker,'activity','Auth failure','Mocked.',{},'auth-failure')
        smtp.return_value.login.side_effect=smtplib.SMTPAuthenticationError(535,b'Invalid authentication')
        process_outbox();delivery=EmailDelivery.objects.get(notification=notice)
        self.assertEqual(delivery.status,'failed');self.assertIn('535',delivery.last_error)
        self.assertNotIn('fake-app-password',delivery.last_error)
        smtp.return_value.send_message.assert_not_called()

    @override_settings(**SMTP_TEST_SETTINGS)
    @patch('marketplace.email_service.smtplib.SMTP')
    def test_pre_send_connection_failure_is_safely_retried(self,smtp):
        self.worker.email='worker@gighouse-test.ug';self.worker.save()
        notice=notify(self.worker,'activity','Connection timeout','Mocked.',{},'connection-failure')
        smtp.side_effect=TimeoutError()
        process_outbox();delivery=EmailDelivery.objects.get(notification=notice)
        self.assertEqual(delivery.status,'retry');self.assertGreater(delivery.next_attempt,timezone.now())
        self.assertEqual(process_outbox()['processed'],0)

    @override_settings(**{**SMTP_TEST_SETTINGS,'GMAIL_SMTP_USE_TLS':False,'GMAIL_SMTP_USE_SSL':True,'GMAIL_SMTP_PORT':465})
    @patch('marketplace.email_service.smtplib.SMTP_SSL')
    @patch('marketplace.email_service.smtplib.SMTP')
    def test_secure_ssl_transport_is_supported(self,smtp,smtp_ssl):
        from .email_service import send_smtp
        smtp_ssl.return_value.send_message.return_value={}
        send_smtp('worker@gighouse-test.ug','Mock SSL','Test text','<p>Test</p>')
        smtp.assert_not_called();smtp_ssl.assert_called_once()
        smtp_ssl.return_value.starttls.assert_not_called()
        smtp_ssl.return_value.login.assert_called_once()
