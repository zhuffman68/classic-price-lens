"""Startup proof uses only our temporary update job and launched child identity."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from price_lens.update_startup import JOB_ENV,TOKEN_ENV,StartupReceipt,wait_for_startup
from price_lens.update_startup_ui import StartupMonitor


class Clock:
    def __init__(self):self.value=0
    def __call__(self):return self.value
    def sleep(self,seconds):self.value+=seconds


class Child:
    pid=12345
    def __init__(self,statuses=()):self.statuses=list(statuses)
    def poll(self):return self.statuses.pop(0) if self.statuses else None


class StartupReceiptTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)/'install';self.root.mkdir()
        self.cache=Path(self.folder.name)/'updates-v1';self.job=self.cache/'job-abcdef';self.job.mkdir(parents=True)
        self.token='a'*64;self.version='1.0.1'
        self.plan=dict(root=str(self.root),startup_token=self.token,offer=dict(manifest=dict(version=self.version)))
        self.write_plan()

    def write_plan(self):
        (self.job/'request.json').write_text(json.dumps(self.plan))

    def take(self,**changes):
        env={JOB_ENV:str(self.job),TOKEN_ENV:self.token,'KEEP':'untouched'};env.update(changes)
        receipt=StartupReceipt.take_environment(self.root,self.cache,self.version,env)
        self.assertNotIn(JOB_ENV,env);self.assertNotIn(TOKEN_ENV,env);self.assertEqual(env['KEEP'],'untouched')
        return receipt

    def test_expected_job_receipt_is_atomic_once_and_contains_only_fixed_fields(self):
        receipt=self.take();self.assertIsNotNone(receipt)
        receipt.report(True);first=(self.job/'started.json').read_bytes();receipt.report(False,'private chat')
        self.assertEqual((self.job/'started.json').read_bytes(),first)
        self.assertEqual(json.loads(first),dict(ready=True,pid=os.getpid(),token=self.token,version=self.version))
        self.assertFalse((self.job/'started.json.tmp').exists())

    def test_untrusted_diagnostic_text_is_replaced_with_a_fixed_error_code(self):
        receipt=self.take();receipt.report(False,'private chat /home/private/draft')
        data=json.loads((self.job/'started.json').read_text())
        self.assertEqual(data['error'],'app-startup-failed');self.assertNotIn('private',(self.job/'started.json').read_text())

    def test_wrong_cache_root_version_nonce_and_malformed_plan_are_rejected(self):
        for mutation in (
            lambda:self.plan.update(root=str(self.root/'other')),
            lambda:self.plan['offer']['manifest'].update(version='1.0.2'),
            lambda:self.plan.update(startup_token='b'*64),
            lambda:self.plan.update(offer=[]),
        ):
            original=json.loads(json.dumps(self.plan));mutation();self.write_plan()
            self.assertIsNone(self.take());self.plan=original;self.write_plan()
        outside=Path(self.folder.name)/'job-other1';outside.mkdir();(outside/'request.json').write_text(json.dumps(self.plan))
        self.assertIsNone(self.take(**{JOB_ENV:str(outside)}))
        bad=self.cache/'unexpected';bad.mkdir();(bad/'request.json').write_text(json.dumps(self.plan))
        self.assertIsNone(self.take(**{JOB_ENV:str(bad)}))
        self.assertIsNone(self.take(**{TOKEN_ENV:'not-a-nonce'}))
        (self.job/'request.json').write_text('{"root":"first","root":"second"}')
        self.assertIsNone(self.take())

    def test_job_owned_by_another_user_is_rejected(self):
        if not hasattr(os,'getuid'):self.skipTest('Unix file ownership')
        with patch('price_lens.update_startup.os.getuid',return_value=os.getuid()+1):self.assertIsNone(self.take())

    def test_oversized_plan_is_rejected_even_if_a_valid_prefix_fits_the_read_limit(self):
        (self.job/'request.json').write_text(json.dumps(self.plan)+' '*600000)
        self.assertIsNone(self.take())

    @unittest.skipUnless(hasattr(os,'O_NOFOLLOW'),'No-follow file descriptors')
    def test_request_symlink_and_non_regular_file_are_rejected_without_blocking(self):
        request=self.job/'request.json';saved=self.job/'saved.json';request.rename(saved)
        request.symlink_to(saved);self.assertIsNone(self.take());request.unlink()
        if hasattr(os,'mkfifo'):
            os.mkfifo(request)
            # No writer is opened: a blocking receipt reader would hang here.
            self.assertIsNone(self.take());request.unlink()
        request.mkdir();self.assertIsNone(self.take())

    def receipt_data(self,**changes):
        data=dict(ready=True,pid=Child.pid,token=self.token,version=self.version);data.update(changes)
        (self.job/'started.json').write_text(json.dumps(data))

    def wait(self,child=None):
        clock=Clock()
        return wait_for_startup(self.job,self.token,self.version,child or Child(),timeout=.3,clock=clock,sleep=clock.sleep)

    def test_wait_accepts_only_current_child_token_version_and_strict_true(self):
        self.receipt_data();self.assertTrue(self.wait())
        for changes in (dict(pid=999),dict(pid=True),dict(token='b'*64),dict(version='old'),dict(ready=1),dict(ready=False)):
            self.receipt_data(**changes);self.assertFalse(self.wait(),changes)
        self.receipt_data();self.assertFalse(self.wait(Child([17])))
        self.assertFalse(self.wait(Child([None,17])))

    def test_wait_handles_late_receipt_and_times_out_missing_or_corrupt_output(self):
        clock=Clock()
        def later(seconds):
            clock.sleep(seconds)
            if clock.value>=.2:self.receipt_data()
        self.assertTrue(wait_for_startup(self.job,self.token,self.version,Child(),timeout=.5,clock=clock,sleep=later))
        (self.job/'started.json').unlink();self.assertFalse(self.wait())
        (self.job/'started.json').write_text('not-json');self.assertFalse(self.wait())

    def test_wait_rejects_oversized_receipt_with_valid_json_prefix(self):
        self.receipt_data()
        with (self.job/'started.json').open('a') as stream:stream.write(' '*10000)
        self.assertFalse(self.wait())

    @unittest.skipUnless(hasattr(os,'O_NOFOLLOW'),'No-follow file descriptors')
    def test_wait_rejects_a_symlink_to_an_otherwise_matching_receipt(self):
        self.receipt_data();path=self.job/'started.json';saved=self.job/'saved.json';path.rename(saved);path.symlink_to(saved)
        self.assertFalse(self.wait())

    def test_receipt_read_past_deadline_cannot_confirm_startup(self):
        clock=Clock()
        def slow_read(*_):
            clock.value=1
            return dict(ready=True,pid=Child.pid,token=self.token,version=self.version)
        with patch('price_lens.update_startup.bounded_json',side_effect=slow_read):
            self.assertFalse(wait_for_startup(self.job,self.token,self.version,Child(),timeout=.3,clock=clock,sleep=clock.sleep))

    def test_installer_receipt_module_does_not_import_the_gui_runtime(self):
        result=subprocess.run([sys.executable,'-B','-c',
            "import sys; import price_lens.update_startup; assert not any(k.startswith('PySide6') for k in sys.modules)"],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))


class StartupMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');cls.app=QApplication.instance() or QApplication([])

    def monitor(self,ready=False,closing=False):
        class Window(QObject):pass
        window=Window();window.closing=closing;window.overlay=SimpleNamespace(ready=ready)
        class Receipt:
            sent=False
            def __init__(self):self.calls=[]
            def report(self,*args):self.calls.append(args);self.sent=True
        receipt=Receipt();clock=Clock();monitor=StartupMonitor(receipt,window,timeout=.2,clock=clock)
        self.addCleanup(monitor.deleteLater);self.addCleanup(monitor.timer.stop);self.addCleanup(window.deleteLater)
        return window,receipt,clock,monitor

    def test_ready_requires_a_running_gui_event_loop_and_versioned_helper_flag(self):
        window,receipt,clock,monitor=self.monitor()
        self.assertEqual(receipt.calls,[])
        QTest.qWait(120);self.assertEqual(receipt.calls,[])
        window.overlay.ready=True;QTest.qWait(120)
        self.assertEqual(receipt.calls,[(True,'overlay-unavailable')]);self.assertFalse(monitor.timer.isActive())

    def test_timeout_or_closing_never_reports_success(self):
        for ready,closing in ((False,False),(True,True)):
            window,receipt,clock,monitor=self.monitor(ready,closing);clock.value=.3
            QTest.qWait(120);self.assertEqual(len(receipt.calls),1);self.assertIs(receipt.calls[0][0],False)
            self.assertIn(receipt.calls[0][1],('overlay-unavailable','startup-timeout'))
            self.assertFalse(monitor.timer.isActive())

    def test_helper_ready_only_after_gui_deadline_cannot_write_a_success_receipt(self):
        window,receipt,clock,monitor=self.monitor()
        clock.value=.3;window.overlay.ready=True;QTest.qWait(120)
        self.assertEqual(receipt.calls,[(False,'startup-timeout')]);self.assertFalse(monitor.timer.isActive())


if __name__=='__main__':unittest.main()
