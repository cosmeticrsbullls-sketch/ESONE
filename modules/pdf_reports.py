"""Private, paginated PDF exports and user initiated file sharing."""
from io import BytesIO
from html import escape
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
FONT=Path(__file__).resolve().parent.parent / "assets/fonts/NotoSansGujarati-Regular.ttf"
pdfmetrics.registerFont(TTFont("ESONE",str(FONT),shapable=True))
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

def pdf_bytes(title,headers,rows,summary=''):
    stream=BytesIO();styles=getSampleStyleSheet()
    for item in styles.byName.values():item.fontName='ESONE';item.shaping=1
    style=styles['BodyText'];style.fontSize=8;style.leading=12
    def cell(value):
        text=str(value if value is not None else '')
        markup=escape(text).replace('\n','<br/>')
        return Paragraph(markup,style)
    size=landscape(A4) if len(headers)>5 else A4
    doc=SimpleDocTemplate(stream,pagesize=size,rightMargin=28,leftMargin=28,topMargin=40,bottomMargin=40)
    story=[Paragraph(escape('ESONE | '+title),styles['Title']),cell(summary),Spacer(1,16)]
    width=size[0]-56
    weights=[3,0.7,1.2,1,1.3] if headers and headers[0]=='Product' else [1]*len(headers)
    widths=[width*w/sum(weights) for w in weights]
    table=Table([[cell(h) for h in headers]]+[[cell(v) for v in r] for r in rows] if rows else [[cell(h) for h in headers],[cell('No matching records')]+['']*(len(headers)-1)],colWidths=widths,repeatRows=1,hAlign='LEFT',splitInRow=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee4cc')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#dddddd')),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(table)
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.drawString(28,20,'Earthshine Professional | ESONE');canvas.drawRightString(size[0]-28,20,'Page '+str(doc.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer);return stream.getvalue()

def pdf_response(title,headers,rows,filename='ESONE_report.pdf',summary=''):
    return Response(pdf_bytes(title,headers,rows,summary),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store'})

def share_button(url,filename='ESONE_report.pdf'):
    return f'<div class="pdf-share" data-pdf="{escape(url,quote=True)}" data-filename="{escape(filename,quote=True)}"><button type="button" class="share-pdf">Share PDF to WhatsApp</button> <a class="secondary" href="{escape(url,quote=True)}">Download PDF</a><p role="status">Prepare the PDF, then choose WhatsApp in your phone share menu.</p></div>'

SHARE_SCRIPT='''<script>document.querySelectorAll('.pdf-share').forEach(box=>{const b=box.querySelector('button');const status=box.querySelector('[role=status]');let file; b.addEventListener('click',async()=>{try{if(!file){b.disabled=true;status.textContent='Preparing PDF…';const r=await fetch(box.dataset.pdf,{credentials:'same-origin'});if(!r.ok||!r.headers.get('content-type').includes('application/pdf'))throw Error();file=new File([await r.blob()],box.dataset.filename,{type:'application/pdf'});b.textContent='Share PDF to WhatsApp';status.textContent='PDF ready. Tap again and choose WhatsApp.';return;}if(navigator.canShare&&navigator.canShare({files:[file]})){await navigator.share({files:[file]});status.textContent='Share menu completed. Check WhatsApp for delivery.';}else{const a=document.createElement('a');const u=URL.createObjectURL(file);a.href=u;a.download=file.name;a.click();setTimeout(()=>URL.revokeObjectURL(u),60000);status.textContent='PDF downloaded. Open WhatsApp and attach this PDF to your chosen chat.';}}catch(e){if(e.name!=='AbortError')status.textContent='Unable to share. Use Download PDF and attach in WhatsApp.';}finally{b.disabled=false;}});});</script>'''
