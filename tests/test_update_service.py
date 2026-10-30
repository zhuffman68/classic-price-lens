"""Async updater behavior with fake releases/helpers; never installs anything."""
import io
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from price_lens.update_service import UpdateService
from price_lens.update_ui import UpdatePanel
from price_lens.updates import Target,read_json,validate_portable
from price_lens.update_install import validate_plan,verify_native_identity
from test_ui_context import FakeSettings
from test_updates import offer,KEYS


class Client:
    def __init__(self,root):self.root=root;self.selected=offer();self.checks=0;self.downloads=0
    def check(self,*args):self.checks+=1;return self.selected
    def download(self,*args):self.downloads+=1;path=self.root/'installer.exe';path.write_bytes(b'fixture only');return path


class Helper:
    def __init__(self):self.stdin=io.BytesIO();self.stopped=False
    def poll(self):return 1 if self.stopped else None
    def terminate(self):self.stopped=True


class UpdateServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup);self.root=Path(self.directory.name)
        self.settings=FakeSettings();self.client=Client(self.root);self.now=1000
        self.service=UpdateService(self.root,self.root,self.settings,client=self.client,
            target=Target('windows-installer-x64',True,self.root),clock=lambda:self.now)

    def tearDown(self):
        self.service.close();self.service.pool.shutdown(wait=True);self.service.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()

    def settle(self):
        deadline=time.monotonic()+3
        while self.service.busy and time.monotonic()<deadline:QTest.qWait(5)
        self.assertFalse(self.service.busy)

    def test_launch_and_configurable_timer_avoid_duplicate_checks_and_notifications(self):
        s=self.service;notices=[];s.available.connect(notices.append)
        s.start();self.assertEqual(s.timer.interval(),360*60000)
        deadline=time.monotonic()+4
        while not self.client.checks and time.monotonic()<deadline:QTest.qWait(5);time.sleep(.001)
        self.settle();self.assertEqual(self.client.checks,1);self.assertEqual(notices,['0.18.0'])
        for _ in range(5):s.check()
        self.assertEqual(self.client.checks,1)
        self.now+=3601;s.check();self.settle();self.assertEqual(self.client.checks,2);self.assertEqual(len(notices),1)
        self.settings.setValue('update-interval-minutes',15);s.configure();self.assertEqual(s.timer.interval(),900000)
        self.settings.setValue('update-interval-minutes',0);s.configure();self.assertFalse(s.timer.isActive())

    def test_download_button_authorizes_install_only_after_helper_is_ready(self):
        s=self.service;s.check();self.settle();restarts=[];s.restart_requested.connect(lambda:restarts.append(True))
        helper=Helper()
        def prepare(cancel):s.helper=helper;return True
        with patch.object(s,'prepare_install',side_effect=prepare):
            s.download_install()
            deadline=time.monotonic()+2
            while not restarts and time.monotonic()<deadline:QTest.qWait(5)
        self.assertEqual(restarts,[True]);self.assertFalse(s.committed);self.assertEqual(helper.stdin.getvalue(),b'')
        self.assertTrue(s.commit());self.assertTrue(s.committed)
        self.assertTrue(read_json(helper.stdin.getvalue())['install'])
        s.close();self.assertFalse(helper.stopped)

    def test_cancelled_authentication_leaves_the_current_app_running(self):
        s=self.service;s.check();self.settle();restarts=[];s.restart_requested.connect(lambda:restarts.append(True))
        with patch.object(s,'prepare_install',side_effect=ValueError('Authentication cancelled')):
            s.download_install();self.settle()
        self.assertFalse(s.closed);self.assertFalse(s.committed);self.assertEqual(restarts,[])
        self.assertEqual(s.state,'available');self.assertIn('cancelled',s.error)

    def test_failed_install_is_visible_after_restart_with_only_one_notice_per_attempt(self):
        (self.root/'last-result.json').write_text('{"ok":false,"version":"0.18.0","attempt":"fixture-1"}')
        self.settings.setValue('update-on-launch',False);notices=[]
        for _ in range(2):
            service=UpdateService(self.root,self.root,self.settings,client=self.client,target=self.service.target,clock=lambda:self.now)
            try:
                service.notice.connect(lambda title,message:notices.append((title,message)));service.start();QTest.qWait(20)
                self.assertIn('did not finish',service.error)
            finally:service.close();service.pool.shutdown(wait=True);service.deleteLater()
        self.assertEqual(len(notices),1)

    def test_update_settings_never_change_the_market_interval(self):
        panel=UpdatePanel(self.service,settings=True)
        try:
            panel.interval.setValue(120);panel.periodic.setChecked(False)
            self.assertEqual(self.settings.values['update-interval-minutes'],0)
            self.assertNotIn('cache-ttl',self.settings.values)
            self.assertFalse(panel.interval.isEnabled())
        finally:panel.deleteLater()

    def test_rate_limit_backoff_keeps_a_long_reset_even_with_a_bad_retry_header(self):
        from urllib.error import HTTPError
        error=HTTPError('https://api.github.com',403,'limited',{'X-RateLimit-Reset':'10000','Retry-After':'bad date'},None);self.addCleanup(error.close)
        self.service.finish('check',None,error)
        self.assertEqual(self.service.not_before,10000)
        self.assertEqual(self.settings.values['update-retry-after'],10000)
        self.now=9999;self.service.check();self.assertEqual(self.client.checks,0)

    def test_native_helper_reverifies_signature_platform_and_newer_version(self):
        selected=offer(target='linux-arch-x64');target=Target('linux-arch-x64',True,self.root)
        plan=dict(root=str(self.root),target=target.name,offer=selected,startup_token='a'*64)
        package,newest,compatible=validate_plan(plan,self.root,'0.17.7',target,KEYS)
        self.assertEqual(package,selected['package']);self.assertEqual(newest,'0.18.0');self.assertFalse(compatible)
        with self.assertRaises(ValueError):validate_plan(plan,self.root,'0.19.0',target,KEYS)
        with self.assertRaises(ValueError):validate_plan({**plan,'target':'linux-debian-x64'},self.root,'0.17.7',target,KEYS)
        with self.assertRaises(ValueError):validate_plan({**plan,'startup_token':''},self.root,'0.17.7',target,KEYS)
        selected['manifest']['artifacts'][target.name]['sha256']='0'*64
        with self.assertRaises(ValueError):validate_plan(plan,self.root,'0.17.7',target,KEYS)

    def test_native_metadata_cannot_install_another_package_or_version(self):
        from types import SimpleNamespace
        for target,output in (('linux-arch-x64','Name : lupin\nVersion : 0.18.0-1\nArchitecture : x86_64'),
                              ('linux-debian-x64','Package: lupin\nVersion: 0.18.0-1\nArchitecture: amd64')):
            with patch('price_lens.update_install.subprocess.run',return_value=SimpleNamespace(stdout=output)):
                verify_native_identity(self.root/'fixture',target,'0.18.0')
                with self.assertRaises(ValueError):verify_native_identity(self.root/'fixture',target,'0.19.0')
            with patch('price_lens.update_install.subprocess.run',return_value=SimpleNamespace(stdout=output.replace('lupin','another-package'))):
                with self.assertRaises(ValueError):verify_native_identity(self.root/'fixture',target,'0.18.0')

    def test_portable_update_rejects_traversal_before_unpacking(self):
        import zipfile
        path=self.root/'portable.zip'
        with zipfile.ZipFile(path,'w') as archive:archive.writestr('../outside.exe',b'bad')
        with self.assertRaises(ValueError):validate_portable(path)
        with zipfile.ZipFile(path,'w') as archive:
            for name in ('runtime/pythonw.exe','price_lens/__init__.py','bin/lupin-screen-reader.exe'):archive.writestr('Lupin-Windows-x64/'+name,b'fixture')
        validate_portable(path)

    def test_external_helper_waits_for_commit_and_app_pipe_closure(self):
        import subprocess
        s=self.service;s.offer=self.client.selected;s.downloaded=self.root/'fixture.exe';s.downloaded.write_bytes(b'not executable')
        s.root=Path(__file__).resolve().parents[1]
        marker=self.root/'committed.json';real_popen=subprocess.Popen
        code="import sys,json,pathlib; print('{\"ready\":true}',flush=True); commit=sys.stdin.buffer.readline(); end=sys.stdin.buffer.read(); pathlib.Path(sys.argv[1]).write_bytes(commit) if end==b'' else None"
        with patch('price_lens.update_service.subprocess.Popen',side_effect=lambda *args,**kwargs:real_popen([__import__('sys').executable,'-B','-c',code,str(marker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)):
            self.assertTrue(s.prepare_install(s.cancelled))
        process=s.helper
        try:
            self.assertFalse(marker.exists());self.assertTrue(s.commit());QTest.qWait(20)
            self.assertFalse(marker.exists())
            process.stdin.close();self.assertEqual(process.wait(timeout=3),0)
            self.assertTrue(read_json(marker.read_bytes())['install'])
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=3)
            process.stdout.close()

    def test_preparing_carries_only_allowlisted_desktop_state_and_uses_job_cwd(self):
        import json
        from types import SimpleNamespace
        s=self.service;s.offer=self.client.selected;s.downloaded=self.root/'fixture.exe';s.downloaded.write_bytes(b'fixture')
        # Use the installed resource root on Windows too; the job/cache remains
        # temporary and Popen below never executes the copied helper.
        s.root=Path(__file__).resolve().parents[1]
        helper=SimpleNamespace(stdout=io.BytesIO(b'{"ready":true}\n'),stdin=io.BytesIO(),poll=lambda:1)
        environment={'DISPLAY':':91','XAUTHORITY':'/owned/auth','GSETTINGS_SCHEMA_DIR':'/custom/schemas'}
        with patch('price_lens.update_service.recovered_environment',return_value=environment), \
                patch('price_lens.update_service.subprocess.Popen',return_value=helper) as spawn:
            self.assertTrue(s.prepare_install(s.cancelled))
        job=Path(spawn.call_args.kwargs['cwd']);plan=json.loads((job/'request.json').read_text())
        self.assertEqual(job.parent,self.root)
        self.assertEqual(plan['relaunch_env'],environment)
        self.assertRegex(plan['startup_token'],r'^[0-9a-f]{64}$')

    def test_starting_result_is_not_announced_and_only_matching_completed_attempt_is_accepted(self):
        s=self.service;notices=[];s.notice.connect(lambda *args:notices.append(args))
        path=self.root/'last-result.json';s.watch_result('job-current')
        for row in (dict(ok=False,status='starting',version='0.18.0',attempt='job-current'),
                    dict(ok=True,status='ready',version='0.18.0',attempt='job-other')):
            path.write_text(__import__('json').dumps(row));s.poll_result()
            self.assertTrue(s.result_timer.isActive());self.assertEqual(notices,[])
        path.write_text('{"ok":true,"status":"ready","version":"0.18.0","attempt":"job-current"}')
        s.poll_result();QTest.qWait(20)
        self.assertFalse(s.result_timer.isActive());self.assertEqual(len(notices),1)
        self.assertEqual(notices[0],('Lupin updated','The updated app is ready.'))

    def test_overlay_startup_failure_is_not_reported_as_a_failed_install_transaction(self):
        s=self.service;notices=[];s.notice.connect(lambda *args:notices.append(args));s.watch_result('job-current')
        (self.root/'last-result.json').write_text('{"ok":false,"status":"failed","reason":"startup","version":"0.18.0","attempt":"job-current"}')
        s.poll_result();QTest.qWait(20)
        self.assertIn('installed',s.error)
        self.assertEqual(len(notices),1);self.assertIn('overlay',notices[0][1])

    def test_legacy_success_waits_for_current_overlay_without_marking_it_notified_early(self):
        s=self.service;notices=[];s.notice.connect(lambda *args:notices.append(args))
        result=dict(ok=True,version='0.18.0',attempt='legacy-job')
        with patch.object(s,'startup_health',return_value=False):
            s.announce_result(result);QTest.qWait(120)
            self.assertEqual(notices,[]);self.assertNotIn('update-result-notified',self.settings.values)
            self.assertTrue(s.ready_notice_timer.isActive())
        with patch.object(s,'startup_health',return_value=True):
            s.poll_ready_notice();QTest.qWait(20)
        self.assertEqual(notices,[('Lupin updated','The updated app is ready.')])
        self.assertFalse(s.ready_notice_timer.isActive())

    def test_legacy_success_becomes_one_startup_warning_if_current_helper_never_readies(self):
        s=self.service;notices=[];s.notice.connect(lambda *args:notices.append(args))
        result=dict(ok=True,version='0.18.0',attempt='legacy-job')
        with patch.object(s,'startup_health',return_value=False):
            s.announce_result(result);s.ready_notice_deadline=0;s.poll_ready_notice();QTest.qWait(20)
            s.announce_result(result);QTest.qWait(20)
        self.assertEqual(len(notices),1);self.assertIn('overlay',notices[0][1])
        self.assertIn('installed',s.error);self.assertFalse(s.ready_notice_timer.isActive())

    def test_close_cancels_legacy_readiness_notice_without_claiming_success(self):
        s=self.service;notices=[];s.notice.connect(lambda *args:notices.append(args))
        with patch.object(s,'startup_health',return_value=False):
            s.announce_result(dict(ok=True,version='0.18.0',attempt='legacy-job'));s.close();QTest.qWait(120)
        self.assertEqual(notices,[]);self.assertFalse(s.ready_notice_timer.isActive())
