import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class StatusTests(unittest.TestCase):
    def invoke(self,root,records=None,flags=(),profile=None,transcript_override=None):
        edl=root/'edl.json';edl.write_text(json.dumps({'version':3,'review_candidates':[]}))
        transcript=root/'actual.json';transcript.write_text(json.dumps(transcript_override or {'events':[{'text':'合成结果'}]}))
        audio=root/'qa.json';audio.write_text(json.dumps({'technical_passed':True,'human_full_length_listen':{'status':'approved','reviewer':'Synthetic human','reviewed_at':'2026-01-01'},**({'profile':profile,'output_sha256':'a'*64} if profile else {})}))
        out=root/'result.json';cmd=[sys.executable,str(ROOT/'scripts/editorial_qa.py'),str(edl),str(transcript),str(audio),'--editorial-reviewer','Synthetic','--editorial-reviewed-at','2026-01-01','--json-out',str(out),'--report-only',*flags]
        if records is not None:
            path=root/'records.json';path.write_text(json.dumps(records));cmd+=['--review-records',str(path)]
        result=subprocess.run(cmd,capture_output=True,text=True)
        return result,json.loads(out.read_text()) if out.exists() else None
    def test_unexecuted_is_not_failed_or_passed(self):
        with tempfile.TemporaryDirectory() as t:
            result,data=self.invoke(Path(t));self.assertEqual(result.returncode,0)
            self.assertEqual(data['check_statuses']['sentence_integrity'],'not_run');self.assertFalse(data['checks']['sentence_integrity']);self.assertFalse(data['release_ready'])
    def test_explicit_failed_blocked_and_not_applicable_remain_distinct(self):
        for status in ('failed','blocked','not_applicable'):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as t:
                result,data=self.invoke(Path(t),{'sentence_integrity':{'status':status}})
                self.assertEqual(result.returncode,0);self.assertEqual(data['check_statuses']['sentence_integrity'],status);self.assertFalse(data['release_ready'])
    def test_browser_or_asr_cannot_certify_actual_listening(self):
        with tempfile.TemporaryDirectory() as t:
            record={'status':'passed','reviewer':'Synthetic','reviewed_at':'2026-01-01','evidence':'play button worked','method':'browser_playback'}
            result,data=self.invoke(Path(t),{'join_listen':record});self.assertNotEqual(result.returncode,0);self.assertIn('cannot be certified',result.stderr)
    def test_actual_output_hash_and_role_are_required_for_preserve_release(self):
        signed={'status':'passed','reviewer':'Synthetic','reviewed_at':'2026-01-01','evidence':'synthetic evidence','method':'actual_listening'}
        records={k:signed for k in ['sentence_integrity','logic_integrity','pacing_integrity','persona_integrity','join_listen']}
        for role,hash_value,expected in [('source','a'*64,False),('post-edit','b'*64,False),('post-edit','a'*64,True)]:
            with self.subTest(role=role,hash=hash_value),tempfile.TemporaryDirectory() as t:
                result,data=self.invoke(Path(t),records,profile='preserve-source',transcript_override={'events':[{'text':'合成结果'}],'audio_role':role,'audio_sha256':hash_value,'timing_review_required':False})
                self.assertEqual(result.returncode,0);self.assertEqual(data['release_ready'],expected)
    def test_projection_is_not_actual_output_transcript(self):
        with tempfile.TemporaryDirectory() as t:
            result,data=self.invoke(Path(t),transcript_override={'events':[{'text':'源转写投影'}],'stage':'mechanical'})
            self.assertEqual(result.returncode,0);self.assertFalse(data['checks']['post_edit_transcript_present']);self.assertFalse(data['release_ready'])
    def test_structured_signed_checks_and_human_listen_can_clear_release(self):
        with tempfile.TemporaryDirectory() as t:
            record={'status':'passed','reviewer':'Synthetic','reviewed_at':'2026-01-01','evidence':'synthetic reviewer fixture','method':'actual_listening'}
            result,data=self.invoke(Path(t),{k:record for k in ['sentence_integrity','logic_integrity','pacing_integrity','persona_integrity','join_listen']})
            self.assertEqual(result.returncode,0);self.assertTrue(data['release_ready'])


if __name__=='__main__':unittest.main()
