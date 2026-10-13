"""Optional Meta utility template. Never substitutes an authentication template."""
import json,os,re,urllib.request,urllib.error
from datetime import timezone
from zoneinfo import ZoneInfo
from modules.otp_delivery import DeliveryError,recipient_number,NoRedirect

def safe_provider_reason(failure,private_values):
    if not isinstance(failure,dict):return ''
    extra=failure.get('error_data',{})
    parts=[failure.get('message',''),extra.get('details','') if isinstance(extra,dict) else '']
    text=' | '.join(value for value in parts if isinstance(value,str) and value.strip())
    for value in sorted((str(v) for v in private_values if v is not None),key=len,reverse=True):
        if len(value)>=3:text=text.replace(value,'[redacted]')
    text=re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]+','[redacted]',text)
    text=re.sub(r'\bEA[A-Za-z0-9]+\b|[A-Za-z0-9_+/=-]{40,}|\d{7,}','[redacted]',text)
    return ' '.join(text.split())[:400]

def send_confirmation(recipient,salon,reference,order_date,total):
    if order_date is None:raise DeliveryError('Order date is missing; no confirmation was sent.')
    if order_date.tzinfo is None:order_date=order_date.replace(tzinfo=timezone.utc)
    local_date=order_date.astimezone(ZoneInfo('Asia/Kolkata'))
    date_text=f'{local_date.day} {local_date:%B %Y}'
    token=os.getenv('WHATSAPP_ACCESS_TOKEN','');sender=os.getenv('WHATSAPP_PHONE_NUMBER_ID','');version=os.getenv('WHATSAPP_API_VERSION','');template=os.getenv('WHATSAPP_ORDER_TEMPLATE','')
    if not token or not sender.isdigit() or not re.fullmatch(r'v\d+\.\d+',version) or not re.fullmatch(r'[a-z0-9_]+',template):raise DeliveryError('Connected WhatsApp order sending needs sender credentials and an approved four-parameter order template. Use Share PDF meanwhile.')
    payload={'messaging_product':'whatsapp','to':recipient_number(recipient),'type':'template','template':{'name':template,'language':{'code':os.getenv('WHATSAPP_ORDER_LANGUAGE','en_US')},'components':[{'type':'body','parameters':[{'type':'text','text':str(v)} for v in [salon,reference,date_text,total]]}]}}
    req=urllib.request.Request(f'https://graph.facebook.com/{version}/{sender}/messages',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as r:result=json.loads(r.read(65536))
        identity=result['messages'][0]['id']
        if not isinstance(identity,str) or not 1<=len(identity)<=150:raise ValueError()
        return identity
    except urllib.error.HTTPError as error:
        # Retain the reason after redacting credentials and order/recipient values.
        details=f'Meta HTTP {error.code}'
        try:
            failure=json.loads(error.read(65536)).get('error',{})
            for key in ('code','error_subcode'):
                value=failure.get(key)
                if type(value) is int:details+=f'; {key} {value}'
            reason=safe_provider_reason(failure,[token,recipient,recipient_number(recipient),sender,salon,reference,date_text,total])
            if reason:details+='; '+reason
        except (OSError,ValueError,AttributeError,TypeError):pass
        raise DeliveryError(details+'. Order confirmation was not accepted. Contact Command Center with this code.') from None
    except (OSError,ValueError,KeyError,IndexError,TypeError):raise DeliveryError('WhatsApp connection or response failed; acceptance is unknown. Check WhatsApp before retrying.') from None
