"""Reset-email transport. HTTPS works without outbound SMTP ports."""
import hashlib
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request

class DeliveryError(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,message,headers,newurl):
        return None

def send(config,message):
    try:
        if config.get('EMAIL_PROVIDER','smtp')=='resend':
            payload={'from':config['EMAIL_FROM'],'to':[message['To']],'subject':message['Subject'],'text':message.get_content()}
            request=urllib.request.Request('https://api.resend.com/emails',data=json.dumps(payload).encode('utf-8'),method='POST',headers={'Authorization':'Bearer '+config['RESEND_API_KEY'],'Content-Type':'application/json','User-Agent':'ESONE/1.0','Idempotency-Key':'esone-reset-'+hashlib.sha256(message.get_content().encode()).hexdigest()})
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=15) as response:
                result=json.loads(response.read(65536))
            if not isinstance(result,dict) or not isinstance(result.get('id'),str) or not result['id']:raise ValueError()
            return result['id']
        with smtplib.SMTP(config['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(config['SMTP_USERNAME'],config['SMTP_PASSWORD'])
            smtp.send_message(message)
        return None
    except (OSError,smtplib.SMTPException,urllib.error.HTTPError,urllib.error.URLError,ValueError,KeyError,TypeError):
        # Never forward provider bodies, reset links, API keys or credentials.
        raise DeliveryError('Email delivery could not be confirmed.') from None
