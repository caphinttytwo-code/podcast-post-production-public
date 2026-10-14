"""Package-wide protections: a working control precedes each dangerous substitution."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'modules/video-conform/scripts'))
import subtitle_review as review
from shared.environment import profile
BASE = '1\n00:00:00,100 --> 00:00:02,000\n墨池深1点8米\n\n2\n00:00:02,100 --> 00:00:03,900\n只有一号馆\n'

class PackageProtection(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.srt=self.root/'source.srt';self.srt.write_text(BASE,encoding='utf-8')
        self.work=self.root/'review'
        review.build_review(self.srt,[{'id':'depth','cue_numbers':[1]}],self.work,media_duration=4,profile='compact-clean')
        self.before=review.sha(self.srt)
        self.assertTrue(review.apply_review(self.work,self.root/'control.srt')['ok'])
    def tearDown(self):
        self.assertEqual(review.sha(self.srt),self.before)
        self.temp.cleanup()
    def cli(self,output):
        return subprocess.run([sys.executable,'-B',str(ROOT/'modules/video-conform/scripts/subtitle_review.py'),'scan-numbers','--srt',str(self.srt),'--output',str(output)],capture_output=True,text=True,encoding='utf-8')
    def test_scan_cli_source_alias(self):
        self.assertEqual(self.cli(self.root/'numbers.json').returncode,0)
        p=self.cli(self.srt);self.assertNotEqual(p.returncode,0);self.assertIn('protected',p.stdout+p.stderr)
    def test_scan_cli_package_output(self):
        self.assertEqual(self.cli(self.root/'numbers.json').returncode,0)
        dest=ROOT/'forbidden-scan.json';self.assertNotEqual(self.cli(dest).returncode,0);self.assertFalse(dest.exists())
    def test_scan_cli_hardlink(self):
        self.assertEqual(self.cli(self.root/'numbers.json').returncode,0)
        dest=self.root/'hard.srt';os.link(self.srt,dest)
        self.assertNotEqual(self.cli(dest).returncode,0);self.assertTrue(dest.exists());self.assertEqual(review.sha(dest),self.before)
    def test_scan_cli_symlink(self):
        self.assertEqual(self.cli(self.root/'numbers.json').returncode,0)
        dest=self.root/'sym.srt';dest.symlink_to(self.srt)
        self.assertNotEqual(self.cli(dest).returncode,0);self.assertTrue(dest.is_symlink())
    def test_build_function_package_output(self):
        dest=ROOT/'forbidden-review'
        with self.assertRaises(ValueError):review.build_review(self.srt,[{'cue_numbers':[1]}],dest,media_duration=4)
        self.assertFalse(dest.exists())
    def test_apply_function_package_output(self):
        dest=ROOT/'forbidden.srt'
        with self.assertRaises(ValueError):review.apply_review(self.work,dest)
        self.assertFalse(dest.exists())
    def test_apply_source_alias(self):
        with self.assertRaises(ValueError):review.apply_review(self.work,self.srt)
        self.assertFalse(self.srt.with_suffix('.review').exists())
    def test_apply_private_hardlink(self):
        private=self.work/'decisions.json';alias=self.root/'state-alias.json';os.link(private,alias)
        before=review.sha(private)
        with self.assertRaises(ValueError):review.apply_review(self.work,self.root/'bad.srt')
        self.assertEqual(review.sha(alias),before);self.assertFalse((self.root/'bad.srt').exists())
    def test_apply_private_symlink(self):
        private=self.work/'baseline.srt';private.unlink();private.symlink_to(self.srt)
        with self.assertRaises(ValueError):review.apply_review(self.work,self.root/'bad.srt')
        self.assertTrue(private.is_symlink())
    def test_fixed_temp_alias_is_never_written(self):
        temp=self.work/'decisions.json.tmp';temp.symlink_to(self.srt)
        state=review.load(self.work/'decisions.json');state['items'][0].update(decision='accept',action_source='individual')
        review.write_json(self.work/'decisions.json',state)
        self.assertTrue(temp.is_symlink());self.assertEqual(review.load(self.work/'decisions.json')['items'][0]['decision'],'accept')
        self.assertFalse(list(self.work.glob('.decisions.json-*.tmp')))
    def test_json_target_hardlink(self):
        dest=self.root/'hard.json';os.link(self.srt,dest)
        review.write_json(self.root/'control.json',{'a':1})
        with self.assertRaises(ValueError):review.write_json(dest,{'a':2})
        self.assertEqual(review.sha(dest),self.before)
    def test_audio_url_boundary(self):
        server=review.make_server(self.work);server.server_close()
        manifest=review.load(self.work/'manifest.json');state=review.load(self.work/'decisions.json')
        manifest['items'][0].update(audio='../source.srt',audio_sha256=self.before)
        state['manifest_sha256']=review.manifest_hash(manifest)
        review.write_json(self.work/'manifest.json',manifest);review.write_json(self.work/'decisions.json',state)
        with self.assertRaises(ValueError):review.make_server(self.work)
    def test_live_manifest_changes_rejected(self):
        server=review.make_server(self.work);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base+'/api/state') as response:self.assertEqual(response.status,200)
            manifest=review.load(self.work/'manifest.json');manifest['items'][0]['question']='changed'
            review.write_json(self.work/'manifest.json',manifest)
            with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(base+'/api/state')
            self.assertEqual(err.exception.code,409);err.exception.close()
        finally:server.shutdown();server.server_close();worker.join()
    def test_live_audio_changes_rejected(self):
        audio=self.root/'audio.bin';audio.write_bytes(b'synthetic-source-audio')
        manifest=review.load(self.work/'manifest.json');state=review.load(self.work/'decisions.json')
        manifest.update(audio_source_path=str(audio),audio_source_sha256=review.sha(audio))
        state['manifest_sha256']=review.manifest_hash(manifest)
        review.write_json(self.work/'manifest.json',manifest);review.write_json(self.work/'decisions.json',state)
        server=review.make_server(self.work);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base+'/api/state') as response:self.assertEqual(response.status,200)
            audio.write_bytes(b'changed-audio')
            with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(base+'/api/state')
            self.assertEqual(err.exception.code,409);err.exception.close()
        finally:server.shutdown();server.server_close();worker.join()
    def test_subtitle_dependencies_do_not_require_production_stack(self):
        # A full conform control has NumPy; subtitle-only has neither codec nor numerical dependencies.
        full=profile('video-conform','full');pure=profile('video-conform','subtitles')
        self.assertIn('numpy',full[0]);self.assertEqual(pure[0],{})
        self.assertEqual(pure[1],[])

if __name__=='__main__':unittest.main()
