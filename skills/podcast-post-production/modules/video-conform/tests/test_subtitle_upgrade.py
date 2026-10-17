import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import subtitle_review as review
from validate_srt import validate_srt
from subtitle_policy import format_policy
from audit_subtitle_sources import audit_sources


def srt(*texts):
    return ''.join(f'{n}\n00:00:{n:02d},000 --> 00:00:{n:02d},900\n{t}\n\n' for n, t in enumerate(texts, 1))


class NumericStyleTests(unittest.TestCase):
    def test_arabic_preserves_notation_and_qualifiers(self):
        for t in ['大概7.5亿次', '不到1%', '可能1‰', '版本2.0', '不到1％', '大概1．8米', '200多档', '两三百人', '一方面', '三星堆']:
            self.assertEqual(review.normalize_compact(t, numeric_style='arabic'), t)
            self.assertTrue(validate_srt(srt(t), media_duration=10, profile='compact-clean', numeric_style='arabic')['ok'])
        self.assertEqual(review.normalize_compact('大概7.5亿次。', numeric_style='arabic'), '大概7.5亿次')
        self.assertEqual(review.normalize_compact('7.5亿次'), '7点5亿次')

    def test_ambiguous_notation_never_collapses(self):
        for t in ['第1、2项', '1.8.3', '2:30', '2026/10/11', '-1.8米', '20℃', '$1.8', '1 %', '1%%', '1‰‰', '10—20', '1 . 8米']:
            self.assertFalse(validate_srt(srt(t), media_duration=10, profile='compact-clean', numeric_style='arabic')['ok'], t)
            with self.assertRaises(ValueError, msg=t):
                review.normalize_compact(t, numeric_style='arabic')

    def test_exact_exceptions_do_not_disable_other_checks(self):
        t=srt('型号C++')
        policy=format_policy(t,[dict(cue_number=1, text='型号C++', literals=['C++'], approval_basis='explicit confirmation')])
        self.assertTrue(validate_srt(t, media_duration=10, profile='compact-clean', format_exceptions=policy)['ok'])
        changed=t.replace('C++','C++。')
        with self.assertRaises(ValueError):validate_srt(changed, media_duration=10, profile='compact-clean', format_exceptions=policy)
        policy=format_policy(changed,[dict(cue_number=1,text='型号C++。',literals=['C++'],approval_basis='explicit confirmation')])
        self.assertFalse(validate_srt(changed, media_duration=10, profile='compact-clean', format_exceptions=policy)['ok'])


class UpgradeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);self.base=self.r/'base.srt'
    def tearDown(self):self.tmp.cleanup()
    def build(self,text,items,**kw):
        self.base.write_text(text);w=self.r/'review';review.build_review(self.base,items,w,media_duration=20,profile='compact-clean',**kw);return w
    def decide(self,w,**updates):
        st=review.load(w/'decisions.json')
        for ident,attrs in updates.items():next(r for r in st['items'] if r['id']==ident).update(attrs,action_source='individual')
        review.write_json(w/'decisions.json',st)
    def test_numeric_all_adds_missing_occurrences_without_propagation(self):
        w=self.build(srt('大概7.5亿次','不到1%','一方面'),[dict(id='views',cue_numbers=[1],suggested_text='大概7.5亿次',unit_note='播放次数',group_label='数值')],numeric_style='arabic',numeric_review='all',protected_terms=['一方面'])
        m=review.load(w/'manifest.json');self.assertEqual(len(m['items']),2)
        self.assertIn('unit_note',m['items'][0]);self.assertEqual(m['items'][0]['unit_note'],'播放次数')
        self.decide(w,views=dict(decision='accept'))
        qa=review.apply_review(w,self.r/'out.srt');self.assertEqual(qa['numeric_unconfirmed_cues'],[2]);self.assertFalse(qa['all_items_human_confirmed'])
        self.assertEqual(self.base.read_text(),(self.r/'out.srt').read_text())
    def test_uncertain_mode_uses_only_explicit_selection(self):
        w=self.build(srt('大概7.5亿次','不到1%'),[dict(id='one',cue_numbers=[1])],numeric_style='arabic')
        self.assertEqual(len(review.load(w/'manifest.json')['items']),1)
    def test_merge_is_explicit_preserves_union_and_unselected_text(self):
        t=srt('秋意','盎然','其他话')
        w=self.build(t,[dict(id='merge',cue_numbers=[1,2],operation='merge',suggested_text='秋意盎然')])
        self.decide(w,merge=dict(decision='edit',corrected_text='秋意盎然'))
        out=self.r/'out.srt';qa=review.apply_review(w,out);new=review.read_cues(out);old=review.read_cues(self.base)
        self.assertEqual(len(new),2);self.assertEqual((new[0].start,new[0].end),(old[0].start,old[1].end));self.assertEqual(new[1].lines,old[2].lines)
        self.assertEqual((new[1].start,new[1].end),(old[2].start,old[2].end))
        self.assertEqual(qa['cue_map'],[dict(old_cue=1,new_cue=1),dict(old_cue=2,new_cue=1),dict(old_cue=3,new_cue=2)])
        self.assertEqual(self.base.read_text(),t)
    def test_accept_or_uncertain_does_not_merge(self):
        for i,decision in enumerate(['accept','uncertain',None]):
            root=self.r/str(i);root.mkdir();base=root/'base.srt';base.write_text(srt('秋意','盎然'))
            w=root/'review';review.build_review(base,[dict(id='x',cue_numbers=[1,2],operation='merge')],w,media_duration=10)
            self.decide(w,x=dict(decision=decision));review.apply_review(w,root/'out.srt')
            self.assertEqual(len(review.read_cues(root/'out.srt')),2)
    def test_nonadjacent_and_overlapping_merge_rejected(self):
        self.base.write_text(srt('甲','乙','丙'))
        with self.assertRaises(ValueError):review.build_review(self.base,[dict(cue_numbers=[1,3],operation='merge')],self.r/'bad',media_duration=10)
        w=self.r/'overlap';review.build_review(self.base,[dict(id='x',cue_numbers=[1,2],operation='merge'),dict(id='y',cue_numbers=[2,3],operation='merge')],w,media_duration=10)
        self.decide(w,x=dict(decision='edit',corrected_text='甲乙'),y=dict(decision='edit',corrected_text='乙丙'))
        with self.assertRaises(ValueError):review.apply_review(w,self.r/'out.srt')
    def test_overlong_merge_remains_pending_and_unconfirmed(self):
        w=self.build(srt('有1人','有2人'),[dict(id='x',cue_numbers=[1,2],operation='merge')],numeric_review='all')
        self.decide(w,x=dict(decision='edit',corrected_text='字'*17));qa=review.apply_review(w,self.r/'out.srt')
        self.assertEqual(qa['numeric_unconfirmed_cues'],[1,2]);self.assertEqual(len(qa['pending']),1)
        self.assertEqual(len(review.read_cues(self.r/'out.srt')),2)
    def test_reviewed_literal_requires_exact_proposal(self):
        w=self.build(srt('型号名称'),[dict(id='x',cue_numbers=[1],suggested_text='型号C++',format_literals=['C++'])])
        self.decide(w,x=dict(decision='edit',corrected_text='型号C++'))
        out=self.r/'out.srt';qa=review.apply_review(w,out);self.assertFalse(qa['pending']);policy=review.load(out.with_suffix('.review')/'format-exceptions.json')
        self.assertTrue(validate_srt(out.read_text(),media_duration=10,profile='compact-clean',format_exceptions=policy)['ok'])
        self.decide(w,x=dict(decision='edit',corrected_text='型号C++。'))
        qa=review.apply_review(w,self.r/'pending.srt');self.assertTrue(qa['pending']);self.assertIn('型号名称',(self.r/'pending.srt').read_text())
    def test_preapproved_exception_is_bound_to_baseline(self):
        t=srt('型号C++');policy=format_policy(t,[dict(cue_number=1,text='型号C++',literals=['C++'],approval_basis='prior approved terminology')])
        w=self.build(t,[dict(id='x',cue_numbers=[1])],format_exceptions=policy)
        qa=review.apply_review(w,self.r/'out.srt');self.assertFalse(qa['all_items_human_confirmed'])
        self.assertEqual(t,(self.r/'out.srt').read_text())
    def test_format_exception_remaps_after_merge(self):
        t=srt('秋意','盎然','型号C++')
        policy=format_policy(t,[dict(cue_number=3,text='型号C++',literals=['C++'],approval_basis='confirmed term')])
        w=self.build(t,[dict(id='x',cue_numbers=[1,2],operation='merge')],format_exceptions=policy)
        self.decide(w,x=dict(decision='edit',corrected_text='秋意盎然'))
        out=self.r/'out.srt';review.apply_review(w,out)
        policy=review.load(out.with_suffix('.review')/'format-exceptions.json')
        self.assertEqual(policy['entries'][0]['cue_number'],2)
        self.assertTrue(validate_srt(out.read_text(),media_duration=10,profile='compact-clean',format_exceptions=policy)['ok'])

    def test_legacy_manifest_missing_new_fields_still_applies(self):
        w=self.build(srt('有1米'),[dict(id='x',cue_numbers=[1])]);m=review.load(w/'manifest.json')
        for k in ['numeric_style','numeric_review','numeric_candidates','format_exceptions']:m.pop(k)
        for item in m['items']:
            for k in ['operation','suggested_text','unit_note','original_text','group_label','format_literals']:item.pop(k)
        review.write_json(w/'manifest.json',m);st=review.load(w/'decisions.json');st['manifest_sha256']=review.manifest_hash(m);st['items'][0].update(decision='edit',corrected_text='有1.8米');review.write_json(w/'decisions.json',st)
        review.apply_review(w,self.r/'out.srt');self.assertIn('有1点8米',(self.r/'out.srt').read_text())


class SourceAuditTests(unittest.TestCase):
    def fixture(self):
        text='1\n00:00:01,000 --> 00:00:02,000\n先开始\n\n'
        return text,{'srt_sha256':hashlib.sha256(text.encode()).hexdigest(), 'records':[dict(id=1,start_ms=1000,end_ms=1500,text='先'),dict(id=2,start_ms=1500,end_ms=1500,text='嗯'),dict(id=3,start_ms=1500,end_ms=2000,text='开始')], 'cues':[dict(cue_number=1,record_ids=[1,2,3],start_anchor_id=1,end_anchor_id=3,before='先嗯开始',after='先开始',reason='去口癖',zero_duration_binding_basis='同一语句中的附和')], 'omissions':[]}
    def test_zero_duration_preserved_and_real_span(self):
        t,m=self.fixture();qa=audit_sources(t,m);self.assertTrue(qa['ok']);self.assertEqual(qa['zero_duration_records'],1);self.assertFalse(qa['semantic_review_completed_by_tool'])
    def test_missing_zero_record_or_binding_is_pending(self):
        t,m=self.fixture();m['cues'][0].update(record_ids=[1,3],before='先开始');self.assertFalse(audit_sources(t,m)['ok'])
        t,m=self.fixture();m['cues'][0].pop('zero_duration_binding_basis');self.assertFalse(audit_sources(t,m)['ok'])
    def test_fake_times_and_unexplained_rewrite_are_rejected(self):
        t,m=self.fixture();m['records'][0]['start_ms']=1100;self.assertFalse(audit_sources(t,m)['ok'])
        t,m=self.fixture();m['cues'][0]['reason']=''
        with self.assertRaises(ValueError):audit_sources(t,m)
    def test_explicit_pending_omission_and_reused_record(self):
        t,m=self.fixture();m['cues'][0].update(record_ids=[1,3],before='先开始');m['omissions']=[dict(record_ids=[2],status='pending',reason='无法绑定语句')];self.assertFalse(audit_sources(t,m)['ok'])
        m['omissions'][0].update(record_ids=[1])
        with self.assertRaises(ValueError):audit_sources(t,m)
    def test_mismatched_snapshot_rejected(self):
        t,m=self.fixture()
        with self.assertRaises(ValueError):audit_sources(t.replace('先开始','先说'),m)


if __name__=='__main__':unittest.main()
