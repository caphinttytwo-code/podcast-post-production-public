import contextlib
import io
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import transcribe_stepfun as asr


def response(text='合成声音'):
    return [{'type':'transcript.text.delta','delta':text,'start_time':10,'end_time':500},
            {'type':'transcript.text.done','text':text}]


class TimingCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.chunks=self.root/'chunks';self.chunks.mkdir();self.out=self.root/'out'
        self.paths=[]
        for i in range(2):
            p=self.chunks/f'chunk-{i:03}.mp3';p.write_bytes(f'synthetic-{i}'.encode());self.paths.append(p)
    def tearDown(self):self.tmp.cleanup()
    def invoke(self,fn,extra=()):
        with mock.patch.object(sys,'argv',['asr',str(self.chunks),str(self.out),*extra]),mock.patch.object(asr,'duration_ms',return_value=1060),mock.patch.object(asr,'credential',return_value='synthetic-only'),mock.patch.object(asr,'transcribe',side_effect=fn),contextlib.redirect_stdout(io.StringIO()):asr.main()
    def test_exact_manifest_ignores_mp3_padding(self):
        manifest=self.root/'manifest.json';manifest.write_text(json.dumps({'sample_rate':44100,'source_frames':88200,'chunks':[
            {'name':p.name,'start_frame':i*44100,'frames':44100,'sha256':asr.sha256(p)} for i,p in enumerate(self.paths)]}))
        self.assertEqual(asr.chunk_timeline(self.paths,manifest),([0,1000],'source_sample_frames'))
        self.invoke(lambda *args:response(),['--manifest',str(manifest)])
        data=json.loads((self.out/'raw-transcript.json').read_text());self.assertEqual(data['chunks'][1]['offset_ms'],1000);self.assertFalse(data['timing_review_required'])
    def test_post_edit_requires_manifest_and_records_actual_audio_role(self):
        with self.assertRaisesRegex(ValueError,'Post-edit ASR requires'):
            self.invoke(lambda *a:(_ for _ in ()).throw(AssertionError('Unexpected upload')),['--transcript-role','post-edit'])
        manifest=self.root/'actual-manifest.json';manifest.write_text(json.dumps({'source_sha256':'a'*64,'sample_rate':16000,'chunks':[{'name':p.name,'start_frame':i*16000,'frames':16000,'sha256':asr.sha256(p)} for i,p in enumerate(self.paths)]}))
        self.invoke(lambda *a:response(),['--manifest',str(manifest),'--transcript-role','post-edit'])
        raw=json.loads((self.out/'raw-transcript.json').read_text());self.assertEqual(raw['audio_role'],'post-edit');self.assertEqual(raw['audio_sha256'],'a'*64)
    def test_pcm_offsets_round_only_after_exact_frame_sum(self):
        paths=[]
        for i in range(4):
            p=self.root/f'{i}.wav'
            with wave.open(str(p),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(44100);w.writeframes(b'\0\0'*441)
            paths.append(p)
        self.assertEqual(asr.chunk_timeline(paths),([0,10,20,30],'pcm_sample_frames'))
    def test_manifest_hash_or_overlap_is_rejected(self):
        path=self.root/'manifest.json';data={'sample_rate':44100,'chunks':[{'name':p.name,'start_frame':i*44100,'frames':44100,'sha256':asr.sha256(p)} for i,p in enumerate(self.paths)]}
        data['chunks'][1]['start_frame']=1;path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'overlapping'):asr.chunk_timeline(self.paths,path)
        data['chunks'][1]['start_frame']=44100;data['chunks'][1]['sha256']='bad';path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'hash'):asr.chunk_timeline(self.paths,path)
    def test_missing_and_zero_timestamps_are_not_fabricated(self):
        events=[{'type':'transcript.text.delta','delta':'缺失'},
                {'type':'transcript.text.delta','delta':'前','start_time':100,'end_time':100},
                {'type':'transcript.text.delta','delta':'真实','start_time':120,'end_time':400},
                {'type':'transcript.text.done','text':'缺失前真实'}]
        self.invoke(lambda *args:events,["--gap-ms","500"])
        raw=json.loads((self.out/'chunk-000.json').read_text());self.assertEqual(raw,events)
        issues=json.loads((self.out/'timing-issues.json').read_text())['issues'];self.assertTrue(any(x['reason']=='missing_or_invalid_timestamp' for x in issues))
        srt=(self.out/'raw-transcript.srt').read_text();self.assertNotIn('缺失',srt);self.assertIn('00:00:00,100 --> 00:00:00,400',srt);self.assertIn('前真实',srt)
        self.assertEqual(asr.grouped_cues([{'delta':'只有疑点','global_start_ms':10,'global_end_ms':10}],24,900),[])
    def test_partial_response_does_not_cache_and_resume_only_requests_failed_chunk(self):
        calls=[]
        def first(path,*args):
            calls.append(path.name)
            return response() if path==self.paths[0] else [{'type':'transcript.text.delta','delta':'未完成'}]
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.invoke(first)
        checksum=asr.sha256(self.out/'chunk-000.json');self.assertFalse((self.out/'chunk-001.json').exists());calls.clear()
        def second(path,*args):calls.append(path.name);return response()
        self.invoke(second);self.assertEqual(calls,['chunk-001.mp3']);self.assertEqual(asr.sha256(self.out/'chunk-000.json'),checksum)
    def test_model_and_audio_cache_binding_mismatch_never_silently_reuses_or_uploads(self):
        self.invoke(lambda *args:response())
        def no_upload(*args):raise AssertionError('Unexpected upload')
        with self.assertRaisesRegex(ValueError,'binding differs'):self.invoke(no_upload,['--model','different-model'])
        self.paths[1].write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'binding differs'):self.invoke(no_upload)
    def test_complete_but_changed_response_is_not_reused(self):
        self.invoke(lambda *args:response())
        (self.out/'chunk-000.json').write_text(json.dumps(response('changed cache')))
        with self.assertRaisesRegex(ValueError,'response hash differs'):
            self.invoke(lambda *args:(_ for _ in ()).throw(AssertionError('Unexpected upload')))
    def test_legacy_adoption_is_explicit_and_does_not_modify_raw_cache(self):
        self.out.mkdir()
        for p in self.paths:(self.out/(p.stem+'.json')).write_text(json.dumps(response()))
        before=asr.sha256(self.out/'chunk-000.json')
        with self.assertRaisesRegex(ValueError,'Legacy cache'):self.invoke(lambda *a:None)
        self.invoke(lambda *a:(_ for _ in ()).throw(AssertionError('Unexpected upload')),['--adopt-legacy-cache'])
        self.assertEqual(asr.sha256(self.out/'chunk-000.json'),before);self.assertTrue((self.out/'chunk-000.request.json').exists())


if __name__=='__main__':unittest.main()
