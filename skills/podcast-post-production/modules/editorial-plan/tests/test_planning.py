import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / 'modules/editorial-plan/scripts/check_plan.py'
spec = importlib.util.spec_from_file_location('planning_checker', SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
from shared.files import sha256


def plan():
    return {'schema_version': '1.0', 'revision': 'synthetic-v01',
            'sources': [{'id': 'main', 'frames': 4800000, 'sample_rate': 48000}],
            'base': {'source_id': 'main', 'start_frame': 0, 'end_frame': 4800000},
            'items': [], 'recommended_ids': [], 'choices': {}}


def cut(i='cut', start=10, end=30):
    return {'id': i, 'action': 'remove', 'start_frame': start*48000,
            'end_frame': end*48000, 'reason': 'Synthetic repetitive explanation; original retained'}


def segment(start, end, source='main', rate=48000):
    return {'source_id': source, 'start_frame': start*rate, 'end_frame': end*rate}


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.p = plan()

    def run_plan(self, items=(), recommended=None):
        self.p['items'] = list(items)
        self.p['recommended_ids'] = list(recommended if recommended is not None else [i['id'] for i in items])
        return checker.audit(self.p, self.directory)

    def choose(self, item, value='apply'):
        evidence = self.directory/'synthetic-review.json'
        evidence.write_text('SYNTHETIC TEST ONLY: no human authorization')
        self.p['choices'][item['id']] = {'choice': value,
            'item_sha256': checker.item_digest(item),
            'source_context_sha256': checker.source_context_digest(self.p),
            'review_ref': {'path': evidence.name, 'sha256': sha256(evidence)}}

    def issue_names(self, r):
        return {i['issue'] for i in r['issues']}

    def test_overlapping_removals_count_union_once(self):
        r = self.run_plan([cut('parent',10,40), cut('child',20,30)])
        self.assertEqual(r['recommendation']['estimated_seconds'],70)
        self.assertEqual(r['recommendation']['removed_union_frames'], [[480000,1920000]])

    def test_proposal_does_not_become_authorized_or_modify_audio(self):
        r = self.run_plan([cut()])
        self.assertEqual(r['recommendation']['estimated_seconds'],80)
        self.assertEqual(r['recorded_apply_choices']['estimated_seconds'],100)
        self.assertEqual(r['pending_recommended_ids'],['cut'])
        self.assertFalse(r['approval_generated'] or r['executable'] or r['audio_modified'])

    def test_keep_choice_cannot_be_overridden_by_recommendation(self):
        item = cut(); self.choose(item,'keep')
        r = self.run_plan([item])
        self.assertEqual(r['recommendation']['estimated_seconds'],100)
        self.assertEqual(r['honored_keep_ids'],['cut'])

    def test_parent_cut_cannot_evade_child_keep(self):
        child = cut('child',20,30); self.choose(child,'keep')
        r = self.run_plan([cut('parent',10,40),child])
        self.assertIn('protected_or_kept_content_consumed',self.issue_names(r))

    def test_kept_move_protects_original_against_other_cuts(self):
        move={'id':'move','action':'move','segments':[segment(10,20)],
              'at_frame':4000000,'reason':'Synthetic relocation'}
        self.choose(move,'keep')
        control=self.run_plan([move],[])
        self.assertEqual(control['recommendation']['estimated_seconds'],100)
        self.assertEqual(control['issues'],[])
        for action in ('remove','replace','move'):
            competing=cut('competing',10,20)
            if action=='replace':competing.update(action=action,segments=[segment(40,45)])
            elif action=='move':
                competing={'id':'competing','action':'move','segments':[segment(10,20)],
                           'at_frame':3000000,'reason':'Synthetic competing relocation'}
            with self.subTest(action=action):
                r=self.run_plan([move,competing],['competing'])
                self.assertIn('protected_or_kept_content_consumed',self.issue_names(r))

    def test_protected_range_detected(self):
        self.p['protected_ranges'] = [segment(20,21)]
        r=self.run_plan([cut()])
        self.assertIn('protected_or_kept_content_consumed',self.issue_names(r))

    def test_recommended_keep_conflict_is_visible(self):
        kept = cut('kept',20,21); kept['action']='keep'
        self.assertIn('protected_or_kept_content_consumed',self.issue_names(self.run_plan([cut(),kept])))

    def test_stale_item_choice_rejected(self):
        item=cut(); self.choose(item); item['end_frame']+=1
        with self.assertRaisesRegex(ValueError,'stale'):
            self.run_plan([item])

    def test_changed_source_context_invalidates_old_choice(self):
        item=cut(); self.choose(item); self.p['sources'][0]['frames']+=1
        with self.assertRaisesRegex(ValueError,'source/version'):
            self.run_plan([item])

    def test_modified_review_evidence_rejected(self):
        item=cut(); self.choose(item)
        (self.directory/'synthetic-review.json').write_text('changed')
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            self.run_plan([item])

    def test_recorded_apply_requires_external_evidence_and_still_is_not_authorization(self):
        item=cut(); self.choose(item)
        r=self.run_plan([item])
        self.assertEqual(r['recorded_apply_choices']['estimated_seconds'],80)
        self.assertFalse(r['executable'])
        self.assertEqual(r['human_approval_authenticity'],'NOT VERIFIED BY THIS CHECKER')
        self.p['choices']['cut'].pop('review_ref')
        with self.assertRaises(ValueError): self.run_plan([item])

    def test_custom_choice_requires_new_ranges(self):
        self.p['choices']['cut']={'choice':'custom','note':'Use a shorter range'}
        r=self.run_plan([cut()])
        self.assertEqual(r['recommendation']['estimated_seconds'],100)
        self.assertIn('custom_choices_need_revised_ranges_and_confirmation',self.issue_names(r))

    def test_hard_target_excess_does_not_make_up_more_cuts(self):
        self.p['runtime']={'kind':'hard','target_seconds':50}
        r=self.run_plan([cut()])
        self.assertEqual(r['recommendation']['estimated_seconds'],80)
        self.assertTrue(r['recommendation']['hard_target_exceeded'])
        self.assertEqual(r['recommendation']['selected_ids'],['cut'])

    def test_move_conserves_content_and_adds_one_pair_of_buffers(self):
        item={'id':'move','action':'move','segments':[segment(10,20)],'at_frame':4000000,
              'reason':'Synthetic ending relocation','buffer_frames':24000}
        r=self.run_plan([item])
        self.assertEqual(r['recommendation']['estimated_seconds'],101)
        self.assertEqual(r['recommendation']['buffer_seconds'],1)

    def test_move_into_itself_rejected(self):
        item={'id':'move','action':'move','segments':[segment(10,20)],'at_frame':600000,'reason':'test'}
        with self.assertRaises(ValueError): self.run_plan([item])

    def test_replacement_counts_old_and_new_once(self):
        item=cut(); item.update(action='replace',segments=[segment(40,45)])
        r=self.run_plan([item])
        self.assertEqual(r['recommendation']['estimated_seconds'],85)

    def test_conflicting_replacements_flagged(self):
        a=cut('a'); a.update(action='replace',segments=[segment(40,45)])
        b=copy.deepcopy(a); b['id']='b'
        self.assertIn('overlapping_structural_operations',self.issue_names(self.run_plan([a,b])))

    def test_whole_block_cannot_silently_be_fine_edited(self):
        item={'id':'insert','action':'insert','segments':[segment(10,11),segment(12,13)],
              'at_frame':4000000,'reason':'test'}
        with self.assertRaisesRegex(ValueError,'Whole'):
            self.run_plan([item])
        item['block_mode']='fine'
        self.assertIn('fine_edit_scope_unconfirmed',self.issue_names(self.run_plan([item])))

    def test_mixed_sample_rates_use_exact_duration(self):
        self.p['sources'].append({'id':'extra','frames':44100,'sample_rate':44100})
        item={'id':'insert','action':'insert','segments':[{'source_id':'extra','start_frame':0,'end_frame':1}],
              'at_frame':4000000,'reason':'test'}
        r=self.run_plan([item])
        self.assertEqual(r['recommendation']['exact_seconds_fraction'],'4410001/44100')

    def test_callback_to_deleted_story_flagged(self):
        self.p['units']=[{'id':'story',**segment(10,20)},
                         {'id':'callback',**segment(40,50),'depends_on':['story']}]
        self.assertIn('dangling_reference',self.issue_names(self.run_plan([cut('story-cut',10,20)])))

    def test_moved_story_remains_available_for_reference(self):
        self.p['units']=[{'id':'story',**segment(10,20)},
                         {'id':'callback',**segment(40,50),'depends_on':['story']}]
        item={'id':'move','action':'move','segments':[segment(10,20)],'at_frame':300000,
              'reason':'Move before callback'}
        self.assertNotIn('dangling_reference',self.issue_names(self.run_plan([item])))

    def test_missing_conditional_edit_flagged(self):
        a=cut('a'); a['requires']=['b']
        r=self.run_plan([a,cut('b',50,60)],['a'])
        self.assertIn('conditional_dependency_missing',self.issue_names(r))

    def test_source_hash_change_rejected(self):
        source=self.directory/'source.txt'; source.write_text('synthetic')
        self.p['sources'][0].update(path=source.name,sha256=sha256(source))
        source.write_text('changed')
        with self.assertRaisesRegex(ValueError,'fingerprint'): self.run_plan()

    def test_bounds_and_integer_frames_are_enforced(self):
        for value in (-1,0.5,True,5000000):
            item=cut(); item['start_frame']=value
            with self.subTest(value=value), self.assertRaises(ValueError): self.run_plan([item])

    def test_cli_guards_source_report_alias_and_fresh_output(self):
        source=self.directory/'source.txt'; source.write_text('synthetic')
        self.p['sources'][0].update(path=source.name,sha256=sha256(source))
        path=self.directory/'plan.json'; path.write_text(json.dumps(self.p))
        original=sha256(source)
        aliases=[source,path,self.directory/'alias.txt',self.directory/'symbolic.txt',ROOT/'forbidden-report.json']
        os.link(source,aliases[2]); aliases[3].symlink_to(source)
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        for target in aliases:
            result=subprocess.run([sys.executable,'-B',str(SCRIPT),str(path),'--report',str(target)],capture_output=True,env=env)
            self.assertEqual(result.returncode,1,result.stdout)
        report=self.directory/'report.json'
        result=subprocess.run([sys.executable,'-B',str(SCRIPT),str(path),'--report',str(report)],capture_output=True,env=env)
        self.assertEqual(result.returncode,0,result.stdout)
        result=subprocess.run([sys.executable,'-B',str(SCRIPT),str(path),'--report',str(report)],capture_output=True,env=env)
        self.assertEqual(result.returncode,1)
        self.assertEqual(sha256(source),original)

    def test_planning_and_legacy_index_preserve_identity_and_no_approval(self):
        from shared.project_index import build_index
        for mode in ('editorial-plan','audio-edit','video-conform','trailers','locked-revision','project-audit'):
            with self.subTest(mode=mode):
                r=build_index({'workflow':mode,'module_version':'synthetic','inputs':[]},self.directory)
                self.assertEqual(r['workflow'],mode)
                self.assertFalse(r['approval_generated'])

    def test_planning_format_blocked_by_legacy_renderer_and_target_branch_keeps_approved_only_gate(self):
        scripts=ROOT/'modules/audio-edit/scripts'
        sys.path.insert(0,str(scripts))
        s=importlib.util.spec_from_file_location('planning_edl_compatibility',scripts/'render_podcast_edl.py')
        renderer=importlib.util.module_from_spec(s);s.loader.exec_module(renderer)
        with self.assertRaisesRegex(ValueError,'Non-executable editorial plan'):
            renderer.validate_edl(self.p)
        edl={'version':3,'branch':'target-runtime',
             'transcript_basis':{'source':'source.json','mechanical':'mechanical.json','semantic_based_on':'mechanical'},
             'cuts':[{'start':10,'end':20,'pass':'semantic','decision_status':'approved',
                      'category':'digression','reason':'Synthetic approved content loss','confidence':'medium'}]}
        self.assertEqual(renderer.validate_edl(edl),3)
        edl['cuts'][0]['decision_status']='pending'
        with self.assertRaisesRegex(ValueError,'not approved'): renderer.validate_edl(edl)

    def test_malformed_planning_version_cannot_fall_back_to_legacy_edl(self):
        scripts=ROOT/'modules/audio-edit/scripts';sys.path.insert(0,str(scripts))
        s=importlib.util.spec_from_file_location('planning_edl_guard',scripts/'render_podcast_edl.py')
        renderer=importlib.util.module_from_spec(s);s.loader.exec_module(renderer)
        self.assertEqual(renderer.validate_edl({'version':1,'cuts':[]}),1)
        for value in (1,None,'invalid','1.0'):
            candidate=copy.deepcopy(self.p);candidate['schema_version']=value
            with self.subTest(schema=value),self.assertRaisesRegex(ValueError,'Non-executable editorial plan'):
                renderer.validate_edl(candidate)
        candidate=copy.deepcopy(self.p);candidate.pop('schema_version')
        with self.assertRaisesRegex(ValueError,'Non-executable editorial plan'):
            renderer.validate_edl(candidate)


if __name__ == '__main__': unittest.main()
