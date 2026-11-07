"""Soft duotone UI icons; decorate controls without rewriting their content."""
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote

INK='#26343e'
GOLD='#c99a39'
# Hand-drawn SVGs remain crisp at mobile and desktop button sizes.
PATHS={
 'sales':'<path fill="#26343e" stroke="none" d="M12 2a8 8 0 0 0-8 8c0 6 8 12 8 12s8-6 8-12a8 8 0 0 0-8-8Z"/><circle cx="12" cy="10" r="3" fill="#fff8e8" stroke="none"/><path stroke="#c99a39" d="m16 21 7-7m-5 0h5v5"/>',
 'collection':'<rect x="2" y="6" width="20" height="15" rx="3" fill="#26343e"/><path stroke="#c99a39" d="m4 6 13-3v3"/><path fill="#c99a39" stroke="#c99a39" d="M16 11h6v6h-6Z"/><path stroke="#fff8e8" stroke-width="1.5" d="M6 10h6m-6 3h6m-5-3c5 0 5 5 0 5l4 4"/>',
 'demo':'<rect x="3" y="5" width="18" height="16" rx="2" fill="#fff8e8"/><path stroke-width="4" d="M4 9h16"/><path d="M8 3v4m8-4v4"/><path stroke="#c99a39" d="m18 13 1.5 3.5L23 18l-3.5 1.5L18 23l-1.5-3.5L13 18l3.5-1.5Z"/><path d="M7 14h2m-2 4h2"/>',
 'order':'<path d="M4 8h16l1 13H3Z" fill="#26343e"/><path stroke="#c99a39" d="M8 8V6a4 4 0 0 1 8 0v2"/><path stroke="#fff8e8" d="m8 15 3 3 5-6"/>',
 'in':'<path d="M14 3h6v18h-6"/><path stroke="#c99a39" d="M2 12h13m-5-5 5 5-5 5"/>',
 'out':'<path d="M10 3H4v18h6"/><path stroke="#c99a39" d="M9 12h13m-5-5 5 5-5 5"/>',
 'reports':'<path d="M5 2h10l5 5v15H5Z" fill="#26343e"/><path fill="#c99a39" stroke="#c99a39" d="M15 2v5h5"/><path stroke="#c99a39" stroke-width="3" d="M9 18v-3m4 3v-6m4 6V9"/>',
 'share':'<circle cx="18" cy="4" r="3" fill="#c99a39" stroke="#c99a39"/><circle cx="5" cy="12" r="3" fill="#26343e"/><circle cx="18" cy="20" r="3" fill="#c99a39" stroke="#c99a39"/><path d="m8 10 7-4m-7 8 7 4"/>',
 'download':'<path d="M4 16v5h16v-5"/><path stroke="#c99a39" d="M12 2v13m-5-5 5 5 5-5"/>',
 'save':'<rect x="3" y="3" width="18" height="18" rx="2" fill="#26343e"/><path fill="#c99a39" stroke="#c99a39" d="M7 3h9v6H7Z"/><path stroke="#fff8e8" d="m7 15 3 3 6-6"/>',
 'edit':'<path fill="#c99a39" stroke="#c99a39" d="m5 15 12-12 4 4L9 19l-5 1Z"/><path d="m14 6 4 4M3 23h18"/>',
 'delete':'<path fill="#26343e" d="m5 7 1 15h12l1-15Z"/><path stroke="#c99a39" d="M3 5h18M9 5V2h6v3m-5 5v8m4-8v8"/>',
 'search':'<circle cx="10" cy="10" r="7" fill="#fff8e8"/><path stroke="#c99a39" stroke-width="3" d="m15 15 7 7"/>',
 'users':'<circle cx="9" cy="7" r="4" fill="#26343e"/><path d="M2 22v-3a7 7 0 0 1 14 0v3" fill="#26343e"/><path stroke="#c99a39" d="M17 4a4 4 0 0 1 0 8m2 4a6 6 0 0 1 3 5"/>',
 'add':'<circle cx="12" cy="12" r="10" fill="#26343e"/><path stroke="#c99a39" d="M6 12h12M12 6v12"/>',
 'check':'<circle cx="12" cy="12" r="10" fill="#26343e"/><path stroke="#c99a39" d="m6 12 4 4 8-8"/>',
 'lock':'<rect x="4" y="10" width="16" height="12" rx="2" fill="#26343e"/><path stroke="#c99a39" d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v3"/>',
 'home':'<path d="m2 11 10-9 10 9" stroke="#c99a39"/><path d="M5 10v12h14V10" fill="#26343e"/><path d="M10 22v-7h4v7" stroke="#c99a39"/>',
 'back':'<path stroke="#c99a39" d="m10 5-7 7 7 7"/><path d="M3 12h19"/>',
 'open':'<rect x="3" y="3" width="18" height="18" rx="4" fill="#26343e"/><path stroke="#c99a39" d="M7 12h10m-4-4 4 4-4 4"/>',
 'bell':'<path d="M4 18h16c-3-3-2-7-3-10a5 5 0 0 0-10 0c-1 3 0 7-3 10Z" fill="#26343e"/><path stroke="#c99a39" d="M10 22h4M12 2v2"/>',
 'call':'<path fill="#26343e" d="M3 3h5l2 5-3 2a16 16 0 0 0 7 7l2-3 5 2v5C10 23 1 14 3 3Z"/><path stroke="#c99a39" d="M15 3a8 8 0 0 1 6 6m-6-2a4 4 0 0 1 2 2"/>',
}

def svg(key):
    return '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="'+INK+'" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+PATHS.get(key,PATHS['open'])+'</svg>'

def action_key(label,href=''):
    label=' '.join(label.casefold().split())
    for needles,key in [
        (('punch out','sign out','logout'),'out'),(('punch in','login','sign in'),'in'),
        (('download','export'),'download'),(('share',),'share'),
        (('delete','remove','cancel'),'delete'),(('password','otp'),'lock'),
        (('save',),'save'),(('edit','reschedule'),'edit'),
        (('search','find','filter','apply'),'search'),
        (('complete','confirm','verify','mark','approve'),'check'),
        (('import','upload'),'add'),(('back','return','previous'),'back'),
        (('notification','message'),'bell'),(('report','history','my visits','my orders'),'reports'),
        (('order',),'order'),(('demo','calendar'),'demo'),
        (('collection',),'collection'),(('call',),'call'),
        (('sales','visit','location','gps','map','check in'),'sales'),
        (('employee','client','salon','team','educator'),'users'),
        (('new','add','create','register'),'add'),(('home','command center'),'home')]:
        if any(word in label for word in needles):return key
    return 'open'

class _Controls(HTMLParser):
    def __init__(self,document):
        super().__init__(convert_charrefs=False)
        self.document=document
        self.lines=[0]
        for match in re.finditer('\n',document):self.lines.append(match.end())
        self.active=[];self.insertions=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in {'svg','img'}:
            for item in self.active:item['graphic']=True
        if tag not in {'button','a'} or 'data-action-icon' in attrs:return
        if tag=='a' and not attrs.get('href'):return
        row,col=self.getpos();at=self.lines[row-1]+col+len(self.get_starttag_text())-1
        self.active.append(dict(tag=tag,at=at,text=[],graphic=False,attrs=attrs))
    def handle_endtag(self,tag):
        if tag not in {'button','a'}:return
        if not self.active or self.active[-1]['tag']!=tag:return
        item=self.active.pop();label=unescape(''.join(item['text'])).strip()
        # Existing icon controls keep one icon; plain branding links are not actions.
        if label and not item['graphic'] and 'esone-brand' not in item['attrs'].get('class','').split():
            self.insertions.append((item['at'],action_key(label,item['attrs'].get('href',''))))
    def handle_data(self,data):
        for item in self.active:item['text'].append(data)
    def handle_entityref(self,name):self.handle_data('&'+name+';')
    def handle_charref(self,name):self.handle_data('&#'+name+';')

def decorate_controls(document):
    parser=_Controls(document);parser.feed(document);parser.close()
    for at,key in sorted(parser.insertions,reverse=True):
        document=document[:at]+' data-action-icon="'+key+'"'+document[at:]
    return document

BASE_CSS='''
[data-action-icon]{--action-art:none;display:inline-flex!important;align-items:center;justify-content:center;gap:9px;vertical-align:middle}
[data-action-icon]::before{content:"";display:inline-block;width:24px;height:24px;flex:0 0 24px;background:#fff8e8 var(--action-art) center/contain no-repeat;border-radius:6px}
.workspace-buttons [data-action-icon]::before{width:36px;height:36px;flex-basis:36px}
.esone-links .nav-icon svg,.module-icon svg{width:24px;height:24px}
@media(max-width:480px){[data-action-icon]{gap:8px}[data-action-icon]::before{width:22px;height:22px;flex-basis:22px}.workspace-buttons [data-action-icon]::before{width:28px;height:28px;flex-basis:28px}}
'''
CSS=BASE_CSS+'\n'.join('[data-action-icon="'+key+'"]{--action-art:url("data:image/svg+xml,'+quote(svg(key),safe='')+'");}' for key in PATHS)
