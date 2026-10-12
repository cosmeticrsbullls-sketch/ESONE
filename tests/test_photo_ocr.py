import fcntl
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from modules.ocr_worker import arrange_lines
from modules.photo_ocr import extract,ExtractionError

class PhotoOcrTests(unittest.TestCase):
    def test_columns_reconstructed_in_row_order(self):
        boxes=[[[20,0],[25,0],[25,10],[20,10]],[[0,0],[10,0],[10,10],[0,10]],[[0,30],[10,30],[10,40],[0,40]]]
        self.assertEqual(arrange_lines(boxes,['100.00','TEST ITEM','Total 100.00']),'TEST ITEM 100.00\nTotal 100.00')
        self.assertEqual(arrange_lines([],[]),'')
    def test_second_job_rejected_without_launching_worker(self):
        with open(Path(tempfile.gettempdir())/'esone-document-ocr.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:
                with patch('modules.photo_ocr.subprocess.run') as run:
                    with self.assertRaisesRegex(ExtractionError,'Another document'):extract(b'test')
                    run.assert_not_called()
            finally:fcntl.flock(lock,fcntl.LOCK_UN)
    def test_worker_failure_and_timeout_are_safe_and_release_lock(self):
        with patch('modules.photo_ocr.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',90)):
            with self.assertRaisesRegex(ExtractionError,'timed out'):extract(b'test')
        with patch('modules.photo_ocr.subprocess.run',return_value=subprocess.CompletedProcess([],1,b'not JSON',b'private error')):
            with self.assertRaisesRegex(ExtractionError,'stopped'):extract(b'test')
        with patch('modules.photo_ocr.subprocess.run',return_value=subprocess.CompletedProcess([],0,b'{"ok":true,"text":"TEST","media_type":"image/png"}',b'')) as run:
            self.assertEqual(extract(b'test'),('TEST','image/png'))
            passed=run.call_args.kwargs['env']
            self.assertNotIn('DATABASE_URL',passed)
            self.assertEqual(passed['OMP_NUM_THREADS'],'1')
            source=Path(run.call_args.args[0][-1])
            self.assertFalse(source.exists())
