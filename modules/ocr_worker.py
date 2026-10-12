"""Short-lived CPU-only OCR worker. Documents never leave this process/server."""
import io
import json
from pathlib import Path
import statistics
import sys

MAX_PIXELS=20_000_000
MAX_SIDE=1800
MAX_TEXT=100_000

def arrange_lines(boxes,texts):
    entries=[]
    for box,text in zip(boxes,texts):
        xs=[float(p[0]) for p in box];ys=[float(p[1]) for p in box]
        entries.append((sum(ys)/len(ys),min(xs),str(text),max(ys)-min(ys)))
    if not entries:return ''
    height=max(1,statistics.median(e[3] for e in entries));groups=[]
    for entry in sorted(entries):
        if not groups or abs(entry[0]-statistics.mean(e[0] for e in groups[-1]))>height*.65:groups.append([])
        groups[-1].append(entry)
    return '\n'.join(' '.join(e[2] for e in sorted(group,key=lambda e:e[1])) for group in groups)

def engine():
    from rapidocr import RapidOCR
    return RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':1,'EngineConfig.onnxruntime.inter_op_num_threads':1,'Det.limit_side_len':512,'Cls.cls_batch_num':1,'Rec.rec_batch_num':1,'Global.log_level':'error','Global.use_cls':False})

def prepare_image(image):
    from PIL import ImageOps
    prepared=ImageOps.exif_transpose(image).convert('RGB')
    prepared.thumbnail((MAX_SIDE,MAX_SIDE))
    return prepared

def read_image(image,ocr):
    output=ocr(image)
    if output.txts is None or output.boxes is None:return ''
    return arrange_lines(output.boxes,output.txts)

def run(data):
    if data.startswith(b'%PDF-'):
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data))
        if reader.is_encrypted or not 1<=len(reader.pages)<=20:raise ValueError('Use an unencrypted PDF with at most 20 pages.')
        texts=[page.extract_text() or '' for page in reader.pages]
        scanned=[index for index,text in enumerate(texts) if len(text.strip())<30]
        if scanned:
            if len(scanned)>5:raise ValueError('Upload scanned PDFs in batches of at most five scanned pages.')
            import pypdfium2 as pdfium
            ocr=engine()
            with pdfium.PdfDocument(data) as document:
                for index in scanned:
                    page=document[index]
                    try:
                        width,height=page.get_size()
                        if width<=0 or height<=0:raise ValueError('Invalid PDF page size.')
                        bitmap=page.render(scale=min(2.5,MAX_SIDE/max(width,height)))
                        try:
                            prepared=prepare_image(bitmap.to_pil())
                            try:texts[index]=read_image(prepared,ocr)
                            finally:prepared.close()
                        finally:bitmap.close()
                    finally:page.close()
        return '\n'.join(texts)[:MAX_TEXT],'application/pdf'
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        media={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}.get(image.format)
        if not media or image.width*image.height>MAX_PIXELS:raise ValueError('Use JPEG, PNG or WebP up to 20 megapixels.')
        image.load()
        prepared=prepare_image(image)
    # Release the original full-resolution image before model inference.
    try:return read_image(prepared,engine())[:MAX_TEXT],media
    finally:prepared.close()

def main():
    try:
        text,media=run(Path(sys.argv[1]).read_bytes())
        if not text.strip():raise ValueError('No text detected. Upload a clearer document.')
        payload=dict(ok=True,text=text,media_type=media)
    except ValueError as error:
        # Only messages authored above are safe; third-party parser errors may contain data.
        allowed={'Use an unencrypted PDF with at most 20 pages.','Upload scanned PDFs in batches of at most five scanned pages.','Invalid PDF page size.','Use JPEG, PNG or WebP up to 20 megapixels.','No text detected. Upload a clearer document.'}
        payload=dict(ok=False,error=str(error) if str(error) in allowed else 'Document could not be read. Try a clear photo or text PDF.')
    except Exception:payload=dict(ok=False,error='Document extraction is unavailable. Please retry or contact Command Center.')
    sys.stdout.write(json.dumps(payload));return 0 if payload['ok'] else 1

if __name__=='__main__':sys.exit(main())
