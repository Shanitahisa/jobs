from html import escape
from django.core.mail.backends.base import BaseEmailBackend
from email.utils import parseaddr
from .email_service import send_smtp,EmailDeliveryError

class GmailSMTPEmailBackend(BaseEmailBackend):
    def __init__(self,fail_silently=False,**kwargs):
        super().__init__(**kwargs)
        self.fail_silently=fail_silently
    def send_messages(self,email_messages):
        sent=0
        for message in email_messages or []:
            try:
                if message.attachments:raise EmailDeliveryError('The notification email backend does not send attachments.')
                html=next((item[0] for item in getattr(message,'alternatives',[]) if item[1]=='text/html'),'<p>'+escape(message.body).replace('\n','<br>')+'</p>')
                for recipient in message.recipients():
                    send_smtp(parseaddr(recipient)[1],message.subject,message.body,html,parseaddr(message.reply_to[0])[1] if message.reply_to else None)
                sent+=1
            except EmailDeliveryError:
                if not self.fail_silently:raise
        return sent
