"""Meta WhatsApp authentication-template transport; credentials stay in server env."""
import json
import os
import re
import urllib.error
import urllib.request


class DeliveryError(Exception):
    pass


def test_mode():
    return os.getenv('ESONE_ENV') == 'test' and os.getenv('RENDER', '').lower() != 'true'


def settings():
    names = ['WHATSAPP_ACCESS_TOKEN', 'WHATSAPP_PHONE_NUMBER_ID', 'WHATSAPP_OTP_TEMPLATE', 'WHATSAPP_API_VERSION']
    values = {key: os.getenv(key, '').strip() for key in names}
    if not all(values.values()):
        raise DeliveryError('WhatsApp OTP is not connected yet. Management must configure the WhatsApp sender and approved OTP template. Your visit remains in progress.')
    if not values['WHATSAPP_PHONE_NUMBER_ID'].isdigit() or not re.fullmatch(r'v\d+\.\d+', values['WHATSAPP_API_VERSION']) or not re.fullmatch(r'[a-z0-9_]+',values['WHATSAPP_OTP_TEMPLATE']):
        raise DeliveryError('WhatsApp OTP configuration needs management review. Your visit remains in progress.')
    values['language'] = os.getenv('WHATSAPP_OTP_LANGUAGE', 'en_US').strip()
    return values


def recipient_number(raw):
    digits = re.sub(r'[\s()+.-]', '', str(raw or ''))
    if len(digits) == 10 and digits.isdigit(): digits = '91' + digits
    if not digits.isascii() or not digits.isdigit() or not 11 <= len(digits) <= 15 or digits.startswith('0'):
        raise DeliveryError('Customer mobile is missing or invalid. Management must update the registered WhatsApp number.')
    return digits


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_otp(recipient, code):
    config = settings()
    number = recipient_number(recipient)
    payload = {'messaging_product':'whatsapp','recipient_type':'individual','to':number,'type':'template',
               'template':{'name':config['WHATSAPP_OTP_TEMPLATE'],'language':{'code':config['language']},
                           'components':[{'type':'body','parameters':[{'type':'text','text':code}]},
                                         {'type':'button','sub_type':'url','index':'0','parameters':[{'type':'text','text':code}]}]}}
    url = f"https://graph.facebook.com/{config['WHATSAPP_API_VERSION']}/{config['WHATSAPP_PHONE_NUMBER_ID']}/messages"
    request = urllib.request.Request(url,data=json.dumps(payload).encode(),method='POST',
                                     headers={'Authorization':f"Bearer {config['WHATSAPP_ACCESS_TOKEN']}",'Content-Type':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=15) as response:
            result = json.loads(response.read(65536))
        message_id = result['messages'][0]['id']
        if not isinstance(message_id,str) or not message_id or len(message_id)>150: raise ValueError()
        return message_id
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError,ValueError,KeyError,IndexError,TypeError):
        # Provider responses can contain personal data, tokens or the OTP; never echo them.
        raise DeliveryError('WhatsApp could not accept the OTP message. Management should check sender access and template approval. Please retry later; your visit remains in progress.') from None
