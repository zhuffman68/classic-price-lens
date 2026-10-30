"""Run the unchanged Windows updater in Linux pwsh, mocking executable actions.

These are script/contract tests, not native Windows installation acceptance.
No installer or Lupin process is executed. Deadline tests call the unchanged
Wait-StartupReceipt function with its explicit, shorter test-only parameter.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / 'price_lens/resources/update-windows.ps1'
WRAPPER = r'''
param([string]$Updater,[string]$Plan,[string]$Scenario,[string]$Record)
$ErrorActionPreference='Stop'
$global:LASTEXITCODE=0
$global:LupinFixtureScenario=$Scenario
$global:LupinFixtureRecord=$Record
function Start-Process {
    [CmdletBinding()]
    param([string]$FilePath,[object[]]$ArgumentList,[switch]$Wait,[switch]$PassThru,[string]$WorkingDirectory)
    $kind=if($Wait){'installer'}elseif($env:LUPIN_UPDATE_JOB){'updated-app'}else{'fallback'}
    $before=$null
    if($kind -eq 'updated-app'){
        $resultPath=Join-Path (Split-Path -Parent $env:LUPIN_UPDATE_JOB) 'last-result.json'
        if(Test-Path -LiteralPath $resultPath){$before=Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json}
    }
    [ordered]@{kind=$kind;file=$FilePath;arguments=@($ArgumentList);pass_thru=[bool]$PassThru;
        working_directory=$WorkingDirectory;process_cwd=[Environment]::CurrentDirectory;
        location=(Get-Location).Path;update_job=$env:LUPIN_UPDATE_JOB;update_token=$env:LUPIN_UPDATE_TOKEN;
        result_at_launch=$before} | ConvertTo-Json -Depth 5 -Compress |
        Add-Content -LiteralPath $global:LupinFixtureRecord -Encoding UTF8
    if($Wait){
        $code=if($global:LupinFixtureScenario -eq 'installer-failure'){13}elseif($global:LupinFixtureScenario -eq 'installer-3010'){3010}else{0}
        return [pscustomobject]@{ExitCode=$code}
    }
    if($kind -eq 'fallback'){return}
    if($global:LupinFixtureScenario -eq 'launch-failure'){throw 'FIXTURE-RAW-STDERR-DO-NOT-PERSIST'}
    $child=[pscustomobject]@{Id=4242;HasExited=($global:LupinFixtureScenario -eq 'child-exit');RefreshCount=0;
        DieOnSecond=($global:LupinFixtureScenario -eq 'dies-after-receipt')}
    $child | Add-Member -MemberType ScriptMethod -Name Refresh -Value {
        $this.RefreshCount++
        if($this.DieOnSecond -and $this.RefreshCount -ge 2){$this.HasExited=$true}
    }
    $receipt=[ordered]@{ready=$true;version='0.99.0';pid=4242;token=$env:LUPIN_UPDATE_TOKEN}
    switch($global:LupinFixtureScenario){
        'wrong-nonce'{$receipt.token=('b'*64)}
        'wrong-pid'{$receipt.pid=4243}
        'string-pid'{$receipt.pid='4242'}
        'wrong-version'{$receipt.version='0.98.0'}
        'string-ready'{$receipt.ready='true'}
        'not-ready'{$receipt.ready=$false;$receipt.error='FIXTURE-CHAT-DRAFT-DO-NOT-PERSIST'}
    }
    $text=$receipt | ConvertTo-Json -Compress
    if($global:LupinFixtureScenario -eq 'malformed-receipt'){$text='{' }
    if($global:LupinFixtureScenario -eq 'oversized-receipt'){$text=' '*8193}
    [IO.File]::WriteAllText((Join-Path $env:LUPIN_UPDATE_JOB 'started.json'),$text,[Text.UTF8Encoding]::new($false))
    return $child
}
& $Updater -Plan $Plan
$code=$LASTEXITCODE
@{kind='wrapper-final';exit_code=$code;update_job=$env:LUPIN_UPDATE_JOB;update_token=$env:LUPIN_UPDATE_TOKEN} |
    ConvertTo-Json -Compress | Add-Content -LiteralPath $Record -Encoding UTF8
exit $code
'''

WAIT_WRAPPER = r'''
param([string]$Updater,[string]$Job,[string]$Mode)
$ErrorActionPreference='Stop'
# Extract the exact function AST, not a rewritten copy or a changed helper.
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Updater,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Parse failure'}
$function=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Wait-StartupReceipt'},$true)
Invoke-Expression $function.Extent.Text
$token='a'*64
$child=[pscustomobject]@{Id=4242;HasExited=$false}
$child | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
if($Mode -eq 'late-read'){
    @{ready=$true;version='0.99.0';pid=4242;token=$token} | ConvertTo-Json -Compress |
        Set-Content -LiteralPath (Join-Path $Job 'started.json') -Encoding UTF8
    function Get-Content {
        param([string]$LiteralPath,[switch]$Raw,[string]$Encoding)
        Start-Sleep -Milliseconds 250
        Microsoft.PowerShell.Management\Get-Content -LiteralPath $LiteralPath -Raw -Encoding UTF8
    }
}
$timer=[Diagnostics.Stopwatch]::StartNew()
$reason=Wait-StartupReceipt -Process $child -Version '0.99.0' -Token $token -Job $Job -TimeoutSeconds 0.12
@{reason=$reason;elapsed=$timer.Elapsed.TotalSeconds;source_default=20} | ConvertTo-Json -Compress
'''


class WindowsUpdateHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cached = ROOT / '.build-tools/powershell-7.6.9/pwsh'
        cls.pwsh = str(cached) if cached.is_file() else shutil.which('pwsh')
        if not cls.pwsh:
            raise unittest.SkipTest('pwsh unavailable; native Windows script acceptance remains separate')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='lupin updater 한글 ')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.install = self.folder / 'Programs 한글 user/Lupin fixture'
        (self.install / 'runtime').mkdir(parents=True)
        (self.install / 'runtime/pythonw.exe').write_bytes(b'fixture placeholder; never executed')
        self.cache = self.folder / 'cache with spaces'
        self.job = self.cache / 'job-한글 space'
        self.job.mkdir(parents=True)
        self.package = self.folder / 'Lupin Setup 한글.exe'
        self.package.write_bytes(b'fixture package; never executed')
        self.token = secrets.token_hex(32)
        self.plan = self.job / 'request.json'
        self.data = dict(root=str(self.install),target='windows-installer-x64',startup_token=self.token,
            package_path=str(self.package),offer=dict(manifest=dict(version='0.99.0'),package=dict(
                bytes=self.package.stat().st_size,sha256=hashlib.sha256(self.package.read_bytes()).hexdigest())))
        self.wrapper = self.folder / 'mock native actions.ps1'
        self.wrapper.write_text(WRAPPER,encoding='utf-8')
        self.record = self.folder / 'actions.jsonl'
        self.env = {**os.environ,'POWERSHELL_TELEMETRY_OPTOUT':'1','DOTNET_CLI_TELEMETRY_OPTOUT':'1',
                    'LUPIN_UPDATE_JOB':'previous-parent-job','LUPIN_UPDATE_TOKEN':'previous-parent-token'}

    def run_helper(self, scenario='success', *, verify_eof=False):
        if scenario == 'bad-initial-hash': self.data['offer']['package']['sha256']='0'*64
        if scenario == 'bad-token': self.data['startup_token']='not-a-64-hex-nonce'
        if scenario == 'job-inside-install':
            self.job = self.install / 'job inside install'
            self.job.mkdir();self.plan=self.job/'request.json'
        self.plan.write_text(json.dumps(self.data,ensure_ascii=False),encoding='utf-8')
        process = subprocess.Popen([self.pwsh,'-NoProfile','-NonInteractive','-File',str(self.wrapper),
            '-Updater',str(UPDATER),'-Plan',str(self.plan),'-Scenario',scenario,'-Record',str(self.record)],
            cwd=self.install,env=self.env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        first = process.stdout.readline()
        response = json.loads(first.decode('utf-8-sig'))
        if response.get('ready'):
            if scenario == 'changed-before-commit':self.package.write_bytes(b'tampered after prepare')
            process.stdin.write(json.dumps(dict(install=scenario!='cancel',resume_capture=True)).encode()+b'\n')
            process.stdin.flush()
            if verify_eof:
                time.sleep(.10)
                self.assertFalse(self.record.exists(),'Executable action happened before parent stdin EOF')
        process.stdin.close();process.stdin=None
        output=process.communicate(timeout=8)[0].decode('utf-8-sig',errors='replace')
        records=[json.loads(line) for line in self.record.read_text(encoding='utf-8-sig').splitlines()] if self.record.exists() else []
        result_path=self.cache/'last-result.json'
        result=json.loads(result_path.read_text(encoding='utf-8-sig')) if result_path.exists() else None
        actions=[row for row in records if row['kind']!='wrapper-final']
        finals=[row for row in records if row['kind']=='wrapper-final']
        self.assertTrue(finals,output)
        self.assertEqual(finals[-1]['update_job'],'previous-parent-job')
        self.assertEqual(finals[-1]['update_token'],'previous-parent-token')
        for row in actions:
            self.assertEqual(row['process_cwd'],str(self.job))
            self.assertEqual(row['location'],str(self.job))
        return process.returncode,response,actions,result,output

    def test_success_waits_for_eof_and_matching_live_receipt_with_unicode_paths(self):
        code,_,actions,result,_=self.run_helper(verify_eof=True)
        self.assertEqual(code,0)
        self.assertEqual([row['kind'] for row in actions],['installer','updated-app'])
        child=actions[-1]
        self.assertTrue(child['pass_thru'])
        self.assertEqual(child['update_job'],str(self.job))
        self.assertEqual(child['update_token'],self.token)
        self.assertEqual(child['working_directory'],str(self.install))
        self.assertEqual(child['arguments'],['-B','-m','price_lens','--capture'])
        self.assertIs(child['result_at_launch']['ok'],False)
        self.assertEqual(child['result_at_launch']['status'],'starting')
        self.assertEqual(result,dict(ok=True,status='ready',version='0.99.0',attempt=self.job.name))

    def test_installer_reboot_required_exit_3010_still_needs_receipt(self):
        code,_,actions,result,_=self.run_helper('installer-3010')
        self.assertEqual(code,0);self.assertIs(result['ok'],True)
        self.assertEqual(actions[-1]['result_at_launch']['status'],'starting')

    def test_failed_child_or_invalid_receipt_never_reports_success_or_launches_duplicate(self):
        cases={'child-exit':'exited','dies-after-receipt':'exited','wrong-nonce':'receipt-invalid',
            'wrong-pid':'receipt-invalid','string-pid':'receipt-invalid','wrong-version':'receipt-invalid',
            'string-ready':'receipt-invalid','not-ready':'not-ready','malformed-receipt':'receipt-invalid',
            'oversized-receipt':'receipt-invalid','launch-failure':'launch-failed'}
        for scenario,detail in cases.items():
            with self.subTest(scenario=scenario):
                # Use a separate fixture so no previous result/receipt can leak.
                if self.record.exists():self.record.unlink()
                code,_,actions,result,output=self.run_helper(scenario)
                self.assertNotEqual(code,0)
                self.assertEqual([row['kind'] for row in actions],['installer','updated-app'])
                self.assertIs(result['ok'],False)
                self.assertEqual(result['status'],'failed')
                self.assertEqual(result['reason'],'startup')
                self.assertEqual(result['detail'],detail)
                self.assertNotIn('DO-NOT-PERSIST',json.dumps(result)+output)

    def test_cancel_and_preparation_failures_do_not_install_or_relaunch(self):
        for scenario in ('cancel','bad-initial-hash','bad-token','job-inside-install'):
            with self.subTest(scenario=scenario):
                if self.record.exists():self.record.unlink()
                code,response,actions,result,_=self.run_helper(scenario)
                self.assertNotEqual(code,0);self.assertEqual(actions,[]);self.assertIsNone(result)
                if scenario=='cancel':self.assertIs(response['ready'],True)
                else:self.assertIn('error',response)
                # Restore only the plan fields changed by this subcase.
                self.data['offer']['package']['sha256']=hashlib.sha256(self.package.read_bytes()).hexdigest()
                self.data['startup_token']=self.token

    def test_tamper_and_installer_failure_reopen_once_without_update_environment(self):
        for scenario,reason,kinds in (('changed-before-commit','package-check-failed',['fallback']),
                                     ('installer-failure','installer-failed',['installer','fallback'])):
            with self.subTest(scenario=scenario):
                if self.record.exists():self.record.unlink()
                self.package.write_bytes(b'fixture package; never executed')
                self.data['offer']['package']=dict(bytes=self.package.stat().st_size,
                    sha256=hashlib.sha256(self.package.read_bytes()).hexdigest())
                code,_,actions,result,output=self.run_helper(scenario)
                self.assertNotEqual(code,0)
                self.assertEqual([row['kind'] for row in actions],kinds)
                self.assertFalse(actions[-1]['update_job']);self.assertFalse(actions[-1]['update_token'])
                self.assertNotIn('--capture',actions[-1]['arguments'])
                self.assertIs(result['ok'],False);self.assertEqual(result['reason'],reason)
                self.assertNotIn('DO-NOT-PERSIST',output)

    def test_missing_and_late_receipts_have_a_bounded_deadline(self):
        wrapper=self.folder/'wait exact helper function.ps1';wrapper.write_text(WAIT_WRAPPER,encoding='utf-8')
        for mode in ('missing','late-read'):
            with self.subTest(mode=mode):
                receipt=self.job/'started.json'
                if receipt.exists():receipt.unlink()
                run=subprocess.run([self.pwsh,'-NoProfile','-NonInteractive','-File',str(wrapper),
                    '-Updater',str(UPDATER),'-Job',str(self.job),'-Mode',mode],env=self.env,
                    check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
                result=json.loads(run.stdout.decode('utf-8-sig'))
                self.assertEqual(result['reason'],'startup-timeout')
                self.assertLess(result['elapsed'],1.5)
        source=UPDATER.read_text()
        self.assertIn('[double]$TimeoutSeconds = 20.0',source)
        self.assertIn('[Math]::Min(200,',source)
        production_call=next(line for line in source.splitlines() if '$startupFailure = Wait-StartupReceipt' in line)
        self.assertNotIn('-TimeoutSeconds',production_call)
        self.assertNotIn('LUPIN_UPDATE_TIMEOUT',source)


if __name__=='__main__':unittest.main()
