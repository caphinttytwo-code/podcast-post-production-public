import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import render_podcast_edl as renderer

ROOT = Path(__file__).resolve().parents[1]
MODE = 'audio-edit'

class FilterFileCompatibilityTests(unittest.TestCase):
    def test_modern_option_is_detected_without_rendering(self):
        with mock.patch.object(renderer.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stderr='')) as run:
            self.assertEqual(renderer.filter_file_option('graph.txt'),'-/filter_complex')
            self.assertIn('-h',run.call_args.args[0])

    def test_legacy_option_only_after_explicit_unsupported_flag(self):
        with mock.patch.object(renderer.subprocess,'run',return_value=subprocess.CompletedProcess([],8,stderr="Unrecognized option '/filter_complex'.")):
            self.assertEqual(renderer.filter_file_option('graph.txt'),'-filter_complex_script')

    def test_other_ffmpeg_probe_errors_not_silently_ignored(self):
        with mock.patch.object(renderer.subprocess,'run',return_value=subprocess.CompletedProcess([],1,stderr='Permission denied reading filter file')):
            with self.assertRaisesRegex(ValueError,'capability check failed'):renderer.filter_file_option('graph.txt')

    def test_actual_render_decode_and_source_preservation(self):
        with tempfile.TemporaryDirectory(prefix='filter-file-compat-') as tmp:
            work = Path(tmp).resolve(); rate=48000
            raw=b''.join(struct.pack('<h',int(11000*math.sin(2*math.pi*330*i/rate))) for i in range(4*rate))
            source=work/'source.wav'
            with wave.open(str(source),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(raw)
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            if MODE=='audio-edit':
                edl=work/'edl.json';edl.write_text(json.dumps({'schema_version':1,'branch':'rigorous-explainer','delivery_formats':['wav'],'cuts':[{'start':1,'end':2}]}))
                output=work/'result.wav'
                command=[sys.executable,'-B',str(ROOT/'scripts/render_podcast_edl.py'),str(source),str(edl),str(output)]
                expected=2.996
            else:
                reference=work/'reference.wav'
                with wave.open(str(reference),'wb') as out:
                    out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(raw[:rate*2]+raw[rate*4:rate*6])
                video=work/'source.mp4'
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=30:duration=4','-i',str(source),'-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(video)],check=True)
                segments=[{'index':i,'source_media_in_seconds':s,'reference_duration':1,'reference_in':f'00:00:0{i}.000','reference_out':f'00:00:0{i+1}.000','reference_in_seconds':i,'reference_out_seconds':i+1} for i,s in enumerate((0,2))]
                manifest=work/'manifest.json';manifest.write_text(json.dumps({'job_id':'synthetic','audio_strategy':'reference-audio-continuous','source_video':str(video),'reference_audio':str(reference),'reference_duration_seconds':2,'segments':segments,'source_timing':{'requires_seek_calibration':False},'output_spec':{'fps':30,'soft_frames':3}}))
                output=work/'result.mp4';expected=2
                command=[sys.executable,'-B',str(ROOT/'scripts/render_reference_conform.py'),str(manifest),'--output',str(output),'--preset','ultrafast','--execute']
            result=subprocess.run(command,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            subprocess.run(['ffmpeg','-v','error','-i',str(output),'-map','0','-f','null','-'],check=True)
            data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)],text=True))
            self.assertAlmostEqual(float(data['format']['duration']),expected,delta=.08)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)

if __name__=='__main__': unittest.main()
