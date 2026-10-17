import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import preserve_pcm as pcm
import render_podcast_edl as renderer


class PreserveTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np=np;self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def source(self,width=3,channels=1,rate=16000):
        p=self.root/f'source-{width}-{channels}.wav'
        limit=1<<(width*8-1);x=self.np.sin(self.np.arange(rate*2)[:,None]*.123)*limit*.08
        if channels==2:x=self.np.c_[x[:,0],-x[:,0]*.6]
        with wave.open(str(p),'wb') as out:
            out.setnchannels(channels);out.setsampwidth(width);out.setframerate(rate);out.writeframes(pcm.encode(x,width))
        return p
    def edl(self):return {'sound_processing':'preserve_source_no_mastering','crossfade_seconds':.02,'cuts':[{'start':.5,'end':.9}]}
    def test_all_integer_depths_and_channels_preserve_body_and_format(self):
        for width in (2,3,4):
            for channels in (1,2):
                with self.subTest(width=width,channels=channels):
                    src=self.source(width,channels);before=src.read_bytes();out=self.root/f'out-{width}-{channels}.wav'
                    report=pcm.assemble(src,out,self.edl())
                    with wave.open(str(out),'rb') as w:
                        self.assertEqual((w.getframerate(),w.getnchannels(),w.getsampwidth()),(16000,channels,width))
                        self.assertEqual(w.getnframes(),25280)
                        body=w.readframes(7680)
                    with wave.open(str(src),'rb') as w:self.assertEqual(body,w.readframes(7680))
                    self.assertTrue(all(pcm.verify(src,out,report).values()));self.assertEqual(src.read_bytes(),before)
    def test_tampered_body_is_detected_even_with_updated_output_hash(self):
        src=self.source();out=self.root/'out.wav';report=pcm.assemble(src,out,self.edl())
        b=bytearray(out.read_bytes());b[1000]^=127;out.write_bytes(b);report['output_sha256']=pcm.digest(out)
        self.assertFalse(pcm.verify(src,out,report)['retained_samples_equal'])
    def test_tampered_fade_is_detected(self):
        src=self.source();out=self.root/'out.wav';report=pcm.assemble(src,out,self.edl())
        with wave.open(str(out),'rb') as f:raw=bytearray(f.readframes(f.getnframes()))
        raw[report['joins'][0]['output_start_frame']*3]^=127
        with wave.open(str(out),'wb') as f:f.setnchannels(1);f.setsampwidth(3);f.setframerate(16000);f.writeframes(raw)
        report['output_sha256']=pcm.digest(out);self.assertFalse(pcm.verify(src,out,report)['crossfades_match_source'])
    def test_short_unapproved_gap_is_rejected_not_eaten(self):
        spec={'sample_rate':16000,'frames':32000}
        with self.assertRaisesRegex(ValueError,'too short'):pcm.layout(spec,[{'start':.4,'end':.8},{'start':.83,'end':1.1}],.02)
    def test_gain_format_changes_source_overwrite_and_existing_output_rejected(self):
        src=self.source()
        for change in ({'pre_gain_db':-3},{'highpass_hz':65},{'sample_rate':48000},{'channels':2},{'wav_bit_depth':16}):
            with self.subTest(change=change),self.assertRaises(ValueError):pcm.assemble(src,self.root/'out.wav',{**self.edl(),**change})
        with self.assertRaises(ValueError):pcm.assemble(src,src,self.edl())
        with self.assertRaises(ValueError):pcm.assemble(src,self.root/'out.mp3',self.edl())
        out=self.root/'ok.wav';pcm.assemble(src,out,self.edl())
        with self.assertRaises(FileExistsError):pcm.assemble(src,out,self.edl())
    def test_dry_run_does_not_write_output(self):
        out=self.root/'none.wav';r=pcm.assemble(self.source(),out,self.edl(),True)
        self.assertFalse(out.exists());self.assertFalse(r['release_ready']);self.assertEqual(r['auditory_review'],'not_run')
    def test_renderer_cli_and_profile_qa_accept_quiet_stereo_16_bit(self):
        src=self.source(2,2);out=self.root/'out.wav';edl={**self.edl(),'version':3,'branch':'rigorous-explainer','transcript_basis':{'source':'s.json','mechanical':'m.json','semantic_based_on':'mechanical'},'delivery_formats':['wav']}
        edl['cuts'][0].update({'pass':'mechanical','decision_status':'approved','category':'false-start','confidence':'high','reason':'Synthetic approved failed take'})
        path=self.root/'edl.json';path.write_text(json.dumps(edl))
        subprocess.run([sys.executable,str(ROOT/'scripts/render_podcast_edl.py'),str(src),str(path),str(out)],check=True,capture_output=True)
        qa=self.root/'qa.json'
        subprocess.run([sys.executable,str(ROOT/'scripts/audio_qa.py'),str(out),'--profile','preserve-source','--source',str(src),'--edl',str(path),'--assembly-map',str(out)+'.assembly.json','--json-out',str(qa)],check=True,capture_output=True)
        result=json.loads(qa.read_text());self.assertTrue(result['technical_passed']);self.assertEqual(result['check_statuses']['integrated_loudness'],'not_applicable');self.assertFalse(result['release_ready'])
    def test_unheard_pause_only_renders_as_review_and_unapproved_cuts_still_rejected(self):
        cut={'start':.5,'end':.9,'pass':'mechanical','decision_status':'approved','category':'content-with-pause-trim',
             'reason':'Synthetic failed take with attached work pause','confidence':'high','trims_adjacent_pause':True,
             'pause_role':'clause','original_gap_seconds':.3,'retained_gap_seconds':.1,'boundary_evidence':['asr','waveform']}
        edl={'version':3,'branch':'rigorous-explainer','transcript_basis':{'source':'source.json','mechanical':'stage.json','semantic_based_on':'mechanical'},'cuts':[cut]}
        with self.assertRaisesRegex(ValueError,'listening'):renderer.validate_edl(edl)
        self.assertEqual(renderer.validate_edl(edl,review_copy=True),3)
        cut['category']='false-start'
        with self.assertRaisesRegex(ValueError,'content-with-pause-trim'):renderer.validate_edl(edl,True)
        cut['category']='content-with-pause-trim';cut['decision_status']='pending'
        with self.assertRaisesRegex(ValueError,'not approved'):renderer.validate_edl(edl,True)


if __name__=='__main__':unittest.main()
