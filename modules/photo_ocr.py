"""Isolated, serialized local document extraction for the Python hosting runtime."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

class ExtractionError(ValueError):
    pass

def extract(data):
    root=Path(__file__).resolve().parent.parent
    # An OS lock spans threads/workers so two OCR processes cannot exhaust RAM.
    with open(Path(tempfile.gettempdir())/'esone-document-ocr.lock','a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ExtractionError('Another document is processing. Please retry shortly.') from None
        try:
            with tempfile.TemporaryDirectory(prefix='esone-ocr-') as directory:
                source=Path(directory)/'document'
                descriptor=os.open(source,os.O_CREAT|os.O_WRONLY|os.O_EXCL,0o600)
                with os.fdopen(descriptor,'wb') as output:output.write(data)
                environment={key:value for key,value in os.environ.items() if key in {'PATH','HOME','LANG','LC_ALL','LD_LIBRARY_PATH','VIRTUAL_ENV','SYSTEMROOT'}}
                environment.update(PYTHONPATH=str(root),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
                try:
                    result=subprocess.run([sys.executable,'-m','modules.ocr_worker',str(source)],cwd=root,env=environment,capture_output=True,timeout=90)
                    payload=json.loads(result.stdout)
                except subprocess.TimeoutExpired:raise ExtractionError('Document processing timed out. Try one clear page at a time.') from None
                except ValueError:raise ExtractionError('Document processing stopped. Try a smaller clear image or a text PDF.') from None
                if result.returncode or not payload.get('ok'):
                    raise ExtractionError(payload.get('error','Document could not be read. Try a clear photo or text PDF.'))
                return payload['text'],payload['media_type']
        finally:fcntl.flock(lock,fcntl.LOCK_UN)
