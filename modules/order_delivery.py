"""Optional Meta utility template. Never substitutes an authentication template."""
import json,os,re,urllib.request,urllib.error
from modules.otp_delivery import DeliveryError,recipient_number,NoRedirect

def send_confirmation(recipient,salon,reference,total):
    token=os.getenv('WHATSAPP_ACCESS_TOKEN','');sender=os.getenv('WHATSAPP_PHONE_NUMBER_ID','');version=os.getenv('WHATSAPP_API_VERSION','');template=os.getenv('WHATSAPP_ORDER_TEMPLATE','')
    if not token or not sender.isdigit() or not re.fullmatch(r'v\d+\.\d+',version) or not re.fullmatch(r'[a-z0-9_]+',template):raise DeliveryError('Connected WhatsApp order sending needs sender credentials and an approved three-parameter order template. Use Share PDF meanwhile.')
    payload={'messaging_product':'whatsapp','to':recipient_number(recipient),'type':'template','template':{'name':template,'language':{'code':os.getenv('WHATSAPP_ORDER_LANGUAGE','en_US')},'components':[{'type':'body','parameters':[{'type':'text','text':str(v)} for v in [salon,reference,total]]}]}}
    req=urllib.request.Request(f'https://graph.facebook.com/{version}/{sender}/messages',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as r:result=json.loads(r.read(65536))
        identity=result['messages'][0]['id']
        if not isinstance(identity,str) or not 1<=len(identity)<=150:raise ValueError()
        return identity
    except (OSError,ValueError,KeyError,IndexError,TypeError):raise DeliveryError('WhatsApp could not accept the order. Check template approval and sender configuration; no successful send is recorded.') from None
