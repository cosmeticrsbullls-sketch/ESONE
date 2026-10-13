"""Optional Meta utility template. Never substitutes an authentication template."""
import json,os,re,urllib.request,urllib.error
from datetime import timezone
from zoneinfo import ZoneInfo
from modules.otp_delivery import DeliveryError,recipient_number,NoRedirect

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
    except (OSError,ValueError,KeyError,IndexError,TypeError):raise DeliveryError('WhatsApp could not accept the order. Check template approval and sender configuration; no successful send is recorded.') from None
