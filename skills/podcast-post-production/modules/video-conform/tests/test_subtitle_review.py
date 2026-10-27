import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import subtitle_review as review
import validate_srt as validator

BASE = '1\n00:00:00,100 --> 00:00:02,000\n墨池有1米80厘米深\n\n2\n00:00:02,100 --> 00:00:03,900\n只有一号馆\n\n3\n00:00:04,000 --> 00:00:05,500\n当时是2010年代\n\n'


class CompactValidationTests(unittest.TestCase):
    def check(self, body, **kwargs):
        return validator.validate_srt('1\n00:00:00,000 --> 00:00:02,000\n'+body+'\n', media_duration=3, profile='compact-clean', **kwargs)

    def test_two_lines_and_prefix_count(self):
        self.assertTrue(self.check('-你先说\n-我接着说')['ok'])
        self.assertFalse(self.check('-'+ '字'*16 + '\n-好')['ok'])
        self.assertFalse(self.check('-你说\n我回答')['ok'])
        self.assertFalse(self.check('-')['ok'])

    def test_screen_limit_lines_symbols_controls(self):
        for body in ['字'*15+'\n'+'字'*15, '一\n二\n三', '话…', '话—话', '话\u200b话', '深1.8米']:
            self.assertFalse(self.check(body)['ok'], body)
        self.assertTrue(self.check('墨池深1点8米')['ok'])

    def test_explicit_limits_and_legacy_behavior(self):
        self.assertTrue(self.check('字'*18, max_chars=20, max_screen_chars=20)['ok'])
        self.assertTrue(validator.validate_srt('1\n00:00:00,000 --> 00:00:02,000\n一\n二\n三\n',media_duration=3)['ok'])
        self.assertTrue(self.check('这句话。', enforce_house_style=False)['ok'])
        with self.assertRaises(ValueError): self.check('一句', max_lines=0)

    def test_invalid_components(self):
        result=validator.validate_srt('1\n00:60:00,000 --> 01:01:00,000\n一句\n',media_duration=4000)
        self.assertFalse(result['ok'])

    def test_numeric_conversion_and_protection(self):
        cases={'墨池大概有1.8米深':'墨池大概有1点8米深', '大概10%':'大概百分之10',
               '其中2/3':'其中3分之2','比例2:1':'比例2比1','比例1.8:1':'比例1点8比1',
               '一号馆七龙珠三分之一':'一号馆七龙珠三分之一','数量1.5/2':'数量2分之1点5', '深1．8米':'深1点8米', '-1米\n-2米':'-1米\n-2米'}
        for before, after in cases.items(): self.assertEqual(review.normalize_compact(before),after)
        self.assertEqual(review.normalize_compact('型号180', ['型号180']), '型号180')
        for text in ['2026/10/11','2026 / 10 / 11','2:30','1.8.3','10--20','1/3%','2/0','-1.8米','1 . 8米','第1、2项','$1.8','20℃','×10','–1米','第1。2项','C++','C#']:
            with self.assertRaises(ValueError, msg=text): review.normalize_compact(text)
        with self.assertRaises(ValueError): review.normalize_compact('型号1.8',['型号1.8'])


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.srt = self.root/'base.srt';self.srt.write_text(BASE)
        self.work = self.root/'review'
        self.items=[{'id':'depth','cue_numbers':[1],'priority':True,'evidence':{'模型A':'1米80 https://example.test/private?token=secret'}},
                    {'id':'brand','cue_numbers':[2]},
                    {'id':'year','cue_numbers':[3],'prior_confirmation':'用户已确认指2010年代'}]
        review.build_review(self.srt,self.items,self.work,media_duration=6,profile='compact-clean')

    def tearDown(self): self.temp.cleanup()

    def save_state(self, mutate):
        state=review.load(self.work/'decisions.json');mutate(state);review.write_json(self.work/'decisions.json',state)
        return state

    def test_partial_submit_snapshot_and_originals(self):
        before=self.srt.read_bytes()
        def edit(state):
            state['items'][0].update(decision='edit',corrected_text='墨池大概有1.8米深',action_source='individual')
        state=self.save_state(edit)
        out=self.root/'new.srt';qa=review.apply_review(self.work,out)
        self.assertEqual(qa['decision_counts'],{'edit':1,'unselected':1,'accept':1})
        self.assertEqual(qa['prior_confirmation_count'],1)
        self.assertFalse(qa['all_items_human_confirmed'])
        self.assertFalse(qa['human_full_audio_review'])
        self.assertIn('墨池大概有1点8米深',out.read_text())
        self.assertEqual(self.srt.read_bytes(),before)
        old=review.read_cues(self.srt);new=review.read_cues(out)
        self.assertEqual([(c.start,c.end) for c in old],[(c.start,c.end) for c in new])
        self.assertEqual(old[1:],new[1:])
        self.assertEqual(review.load(out.with_suffix('.review')/'submitted-decisions.json'),state)
        with self.assertRaises(FileExistsError): review.apply_review(self.work,out)
        self.assertNotIn('token=secret', (self.work/'manifest.json').read_text())

    def test_changed_source_or_manifest_and_duplicate_ids(self):
        self.srt.write_text(BASE.replace('一号馆','别的名称'))
        with self.assertRaises(ValueError): review.apply_review(self.work,self.root/'out.srt')
        self.srt.write_text(BASE)
        state=review.load(self.work/'decisions.json');state['items'][1]['id']='depth'
        review.write_json(self.work/'decisions.json',state)
        with self.assertRaises(ValueError): review.apply_review(self.work,self.root/'out.srt')

    def test_changed_target_manifest_is_rejected(self):
        manifest=review.load(self.work/'manifest.json');manifest['items'][0]['targets'][0]['cue_number']=2
        review.write_json(self.work/'manifest.json',manifest)
        with self.assertRaises(ValueError): review.apply_review(self.work,self.root/'out.srt')

    def test_split_reflow_uncertain_pending_no_fake_times(self):
        def edit(state):
            state['items'][0].update(decision='edit',corrected_text='一句\n\n另开一句',action_source='individual')
            state['items'][1].update(decision='uncertain',note='听不清楚',action_source='individual')
        self.save_state(edit)
        qa=review.apply_review(self.work,self.root/'draft.srt')
        self.assertEqual(len(qa['pending']),2)
        self.assertEqual(qa['status'],'review_draft')
        self.assertEqual(review.read_cues(self.root/'draft.srt'),review.read_cues(self.srt))

    def test_overlong_and_ambiguous_edits_remain_pending(self):
        for i, text in enumerate(['字'*17, '日期2026/10/11', '-只有单行']):
            self.save_state(lambda state: state['items'][0].update(decision='edit', corrected_text=text, action_source='individual'))
            qa=review.apply_review(self.work,self.root/f'pending-{i}.srt')
            self.assertEqual(len(qa['pending']),1)
            self.assertEqual(review.read_cues(self.root/f'pending-{i}.srt'),review.read_cues(self.srt))

    def test_noncontiguous_targets_do_not_replace_middle(self):
        work=self.root/'other'
        review.build_review(self.srt,[{'id':'two','cue_numbers':[1,3]}],work,media_duration=6,profile='compact-clean')
        state=review.load(work/'decisions.json');state['items'][0].update(decision='edit',corrected_text='墨池有1.8米深\n\n当时是2010年代',action_source='individual')
        review.write_json(work/'decisions.json',state)
        out=self.root/'two.srt';review.apply_review(work,out)
        self.assertEqual(review.read_cues(out)[1],review.read_cues(self.srt)[1])

    def test_numbers_and_fixed_terms(self):
        scan=review.scan_numbers(self.srt, ['一号馆'])
        self.assertEqual([x['cue_numbers'] for x in scan],[[1],[3]])
        duplicate=self.root/'duplicate.srt';duplicate.write_text(BASE.replace('\n\n2\n','\n\n1\n'))
        with self.assertRaises(ValueError): review.scan_numbers(duplicate)
        with self.assertRaises(ValueError): review.build_review(self.srt,[self.items[0],self.items[0]],self.root/'bad',media_duration=6)

    def test_server_partial_save_stale_and_cross_origin(self):
        server=review.make_server(self.work)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            def post(state,origin=base):
                req=urllib.request.Request(base+'/api/save',data=json.dumps(state).encode(),headers={'Content-Type':'application/json','Origin':origin})
                return urllib.request.urlopen(req)
            data=json.load(urllib.request.urlopen(base+'/api/state'))
            state=data['state'];state['items'][0].update(decision='accept',action_source='individual')
            self.assertEqual(json.load(post(state))['revision'],1)
            saved=review.load(self.work/'decisions.json')
            self.assertIsNone(saved['items'][1]['decision'])
            self.assertTrue(saved['items'][0]['reviewed_at'])
            with self.assertRaises(urllib.error.HTTPError) as stale: post(state)
            self.assertEqual(stale.exception.code,409)
            stale.exception.close()
            with self.assertRaises(urllib.error.HTTPError) as foreign: post(saved,'http://example.test')
            self.assertEqual(foreign.exception.code,403)
            foreign.exception.close()
            with self.assertRaises(urllib.error.HTTPError) as missing: urllib.request.urlopen(base+'/../baseline.srt')
            missing.exception.close()
        finally:
            server.shutdown();server.server_close();worker.join()

    def test_style_overrides_are_recorded_and_applied(self):
        work=self.root/'style'
        review.build_review(self.srt,[self.items[0]],work,media_duration=6,profile='compact-clean',
                            validation_overrides={'max_chars':24,'max_screen_chars':40,'enforce_house_style':False})
        state=review.load(work/'decisions.json');state['items'][0].update(decision='edit',corrected_text='字'*20+'。',action_source='individual')
        review.write_json(work/'decisions.json',state)
        qa=review.apply_review(work,self.root/'style.srt')
        self.assertEqual(qa['limits']['max_chars'],24)
        self.assertEqual(len(qa['changes']),1)
        self.assertIn('。',(self.root/'style.srt').read_text())
        self.assertFalse(qa['semantic_review_completed_by_tool'])

    def test_actual_clip_decode(self):
        audio=self.root/'tone.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=6',str(audio)],check=True)
        clipwork=self.root/'clips'
        manifest=review.build_review(self.srt,[self.items[0]],clipwork,audio=audio,profile='compact-clean',context_seconds=.5)
        clip=clipwork/manifest['items'][0]['audio']
        self.assertEqual(review.sha(clip),manifest['items'][0]['audio_sha256'])
        self.assertGreater(validator.video_duration(clip),2)
        self.assertLess(validator.video_duration(clip),3)


if __name__ == '__main__': unittest.main()
