import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import prepare_asr_chunks as prepare
import transcribe_stepfun as asr


class ProxyTests(unittest.TestCase):
    def test_real_proxies_keep_exact_source_offsets_and_resume_without_encoding(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source.wav';out=root/'chunks'
            with wave.open(str(source),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100);f.writeframes(b'\0\0\0\0'*44100)
            before=asr.sha256(source);data=prepare.prepare(source,out,.4)
            self.assertEqual([c['start_frame'] for c in data['chunks']],[0,17640,35280]);self.assertEqual(data['chunks'][-1]['frames'],8820)
            paths=sorted(out.glob('chunk-*.mp3'));self.assertEqual(asr.chunk_timeline(paths,out/'manifest.json')[0],[0,400,800])
            hashes=[asr.sha256(p) for p in paths]
            with mock.patch.object(prepare.subprocess,'run',side_effect=AssertionError('Unexpected re-encode')):self.assertEqual(prepare.prepare(source,out,.4),data)
            self.assertEqual([asr.sha256(p) for p in paths],hashes);self.assertEqual(asr.sha256(source),before)
    def test_proxy_binding_mismatch_refuses_changed_source(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source.wav';out=root/'chunks'
            with wave.open(str(source),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*1600)
            prepare.prepare(source,out,1);source.write_bytes(source.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'differ'):prepare.prepare(source,out,1)


if __name__=='__main__':unittest.main()
