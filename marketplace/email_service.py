from datetime import timedelta
from html import escape
from urllib.parse import urlencode
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr,make_msgid,parseaddr
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from .models import EmailDelivery,NotificationPreference


class EmailDeliveryError(Exception):
    def __init__(self,message,status=None,uncertain=False,retryable=False):
        super().__init__(message);self.status=status;self.uncertain=uncertain;self.retryable=retryable


def configured():
    return bool(settings.EMAIL_NOTIFICATIONS_ENABLED and settings.GMAIL_SMTP_HOST and settings.GMAIL_SMTP_USER and settings.GMAIL_SMTP_PASSWORD)


def safe_recipient(email):
    try:validate_email(email)
    except ValidationError:return False
    domain=email.rsplit('@',1)[-1].lower()
    return not (domain.endswith(('.demo','.test','.invalid','.example','.localhost')) or domain in ['example.com','example.net','example.org','localhost'])


def send_smtp(recipient,subject,text,html,reply_to=None,message_id=None):
    if not configured():raise EmailDeliveryError('Gmail SMTP account and app password are not configured.')
    if not safe_recipient(recipient):raise EmailDeliveryError('Fictional or invalid recipient addresses are not sent.')
    sender_name,sender=parseaddr(settings.DEFAULT_FROM_EMAIL)
    try:validate_email(sender)
    except ValidationError:raise EmailDeliveryError('Configure a valid Gmail sender email.')
    if settings.GMAIL_SMTP_USE_TLS==settings.GMAIL_SMTP_USE_SSL:
        raise EmailDeliveryError('Enable exactly one secure transport: STARTTLS (587) or SSL (465).')
    message=EmailMessage()
    message['Subject']=subject
    message['From']=formataddr((sender_name or settings.GMAIL_SENDER_NAME,sender))
    message['To']=recipient
    message['Message-ID']=message_id or make_msgid(domain=sender.rsplit('@',1)[-1])
    reply=reply_to or settings.GMAIL_REPLY_TO_EMAIL
    if reply:
        try:validate_email(reply)
        except ValidationError:raise EmailDeliveryError('Configure a valid reply-to email.')
        message['Reply-To']=reply
    message.set_content(text)
    message.add_alternative(html,subtype='html')
    connection=None;data_started=False
    try:
        context=ssl.create_default_context()
        if settings.GMAIL_SMTP_USE_SSL:
            connection=smtplib.SMTP_SSL(settings.GMAIL_SMTP_HOST,settings.GMAIL_SMTP_PORT,timeout=12,context=context)
        else:
            connection=smtplib.SMTP(settings.GMAIL_SMTP_HOST,settings.GMAIL_SMTP_PORT,timeout=12)
            connection.ehlo();connection.starttls(context=context);connection.ehlo()
        connection.login(settings.GMAIL_SMTP_USER,settings.GMAIL_SMTP_PASSWORD)
        data_started=True
        refused=connection.send_message(message,from_addr=sender,to_addrs=[recipient])
        if refused:
            code=next(iter(refused.values()))[0]
            raise EmailDeliveryError(f'Gmail SMTP refused the recipient (code {code}).',status=code,retryable=400<=code<500)
    except smtplib.SMTPRecipientsRefused as exc:
        code=next(iter(exc.recipients.values()))[0]
        raise EmailDeliveryError(f'Gmail SMTP refused the recipient (code {code}).',status=code,retryable=400<=code<500)
    except smtplib.SMTPResponseException as exc:
        raise EmailDeliveryError(f'Gmail SMTP rejected the request (code {exc.smtp_code}). Check the app password, account permissions and sending limits.',status=exc.smtp_code,retryable=400<=exc.smtp_code<500)
    except (OSError,smtplib.SMTPServerDisconnected):
        raise EmailDeliveryError('SMTP response is uncertain. Check the sending account before retrying.' if data_started else 'Could not connect securely to Gmail SMTP. A retry is scheduled.',uncertain=data_started,retryable=not data_started)
    except smtplib.SMTPException:
        raise EmailDeliveryError('Gmail SMTP could not complete the request.',uncertain=data_started)
    finally:
        if connection:
            try:connection.close()
            except (OSError,smtplib.SMTPException):pass
    return str(message['Message-ID'])


def email_content(notification):
    params={'view':notification.target.get('page','notifications'),'notification':notification.pk}
    for key in ['opportunity_id','engagement_id']:
        if notification.target.get(key):params[key]=notification.target[key]
    url=settings.FRONTEND_URL.rstrip('/')+'/?'+urlencode(params)
    title=escape(notification.title);message=escape(notification.message)
    text=f'{notification.title}\n\n{notification.message}\n\nOpen Gig House: {url}\n\nManage email preferences in Notifications.'
    html=f'''<!doctype html><html><body style="margin:0;background:#f3f3ec;font-family:Arial,sans-serif;color:#222"><div style="max-width:560px;margin:32px auto;padding:32px;background:white;border:1px solid #e3e3d8;border-radius:16px"><div style="font-size:23px;font-weight:bold;letter-spacing:-1px;margin-bottom:30px">⌂ gig house</div><h1 style="font-size:25px;line-height:1.3">{title}</h1><p style="font-size:15px;line-height:1.8;color:#696957">{message}</p><a href="{escape(url,quote=True)}" style="display:inline-block;margin:18px 0;padding:14px 22px;border-radius:8px;background:#20201c;color:white;text-decoration:none">Open Gig House ↗</a><p style="font-size:11px;line-height:1.8;color:#999980">Manage email preferences in Notifications.</p></div></body></html>'''
    return text,html


def process_outbox(limit=30):
    if not configured():return {'accepted':0,'processed':0,'configured':False}
    now=timezone.now()
    # An interrupted SMTP send might already have been accepted: never resend blindly.
    EmailDelivery.objects.filter(status='sending',claimed_at__lt=now-timedelta(minutes=5)).update(status='uncertain',last_error='Sender interrupted. Check the sending account before retrying.')
    accepted=processed=0
    for _ in range(limit):
        with transaction.atomic():
            item=EmailDelivery.objects.select_for_update(skip_locked=True).filter(status__in=['queued','retry'],next_attempt__lte=timezone.now(),attempts__lt=5).order_by('created_at').first()
            if not item:break
            item.status='sending';item.attempts+=1;item.claimed_at=timezone.now();item.save(update_fields=['status','attempts','claimed_at'])
        processed+=1
        notification=item.notification;user=notification.user
        pref,_=NotificationPreference.objects.get_or_create(user=user)
        category_enabled=getattr(pref,{'opportunity':'opportunity_alerts','payment':'payment_alerts'}.get(notification.category,'activity_alerts'))
        if not user.is_active or not pref.email_enabled or not category_enabled or not safe_recipient(user.email):
            item.status='suppressed';item.last_error='Recipient or notification preference does not permit this email.'
        else:
            text,html=email_content(notification)
            try:
                sender=parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
                item.provider_id=send_smtp(user.email,notification.title,text,html,message_id=f'<gighouse-notification-{notification.pk}@{sender.rsplit("@",1)[-1]}>')
                item.status='accepted';item.last_error='';accepted+=1
            except EmailDeliveryError as exc:
                item.status='uncertain' if exc.uncertain else ('retry' if exc.retryable and item.attempts<5 else 'failed')
                item.last_error=str(exc);item.next_attempt=timezone.now()+timedelta(minutes=2**item.attempts)
        item.save(update_fields=['status','provider_id','last_error','next_attempt'])
    return {'accepted':accepted,'processed':processed,'configured':True}
