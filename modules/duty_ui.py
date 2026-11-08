"""Visible attendance prompts complement (never replace) transactional server guards."""
import re
from urllib.parse import urlsplit
from modules.duty import OFFICE_ROLES, notice

def gate_controls(document, path, role, working, can_finish=False):
    if working:return document
    office=role in OFFICE_ROLES
    def protected(target):
        return bool(re.fullmatch(r'/visits/(?:create|[0-9]+/(?:start|complete|request-end-otp|verify-end-otp))',target) or target=='/field/start' or (not office and target in {'/orders','/salons/new','/demos','/calls'}))
    def form(match):
        block=match[0]; opening=block[:block.find('>')+1]
        if not re.search(r'method=[\"\']?post',opening,re.I):return block
        action=re.search(r'action=[\"\']([^\"\']*)',opening,re.I)
        target=urlsplit(action[1]).path if action else path
        demo=bool(re.fullmatch('/demos/[0-9]+',target) and 'value="START"' in block)
        completion=bool(re.fullmatch(r'/visits/[0-9]+/(?:complete|request-end-otp|verify-end-otp)',target) or (re.fullmatch('/demos/[0-9]+',target) and 'value="COMPLETE"' in block))
        if can_finish and completion:return block
        if not protected(target) and not demo and not completion:return block
        # Retain the form as readable evidence; disable its fields and submit button.
        return notice()+opening+'<fieldset disabled aria-disabled="true">'+block[len(opening):block.rfind('</form>')]+'</fieldset></form>'
    document=re.sub(r'<form\b[^>]*>.*?</form>',form,document,flags=re.I|re.S)
    def link(match):
        target=urlsplit(match[2]).path
        if target in {'/field/intake'} or (not office and target in {'/orders/new','/salons/new','/demos/new','/calls/new'}):
            return match[1]+'href="/attendance" title="Punch In first" data-duty-required="true"'
        return match[0]
    return re.sub(r'(<a\b[^>]*?)href=[\"\']([^\"\']+)[\"\']',link,document,flags=re.I)
