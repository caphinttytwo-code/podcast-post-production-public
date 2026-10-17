"""Offline behavioral tests with independent synthetic voices; no real media."""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import multitrack as mt
import preserve_pcm as pcm
import review


class MultitrackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.rate=8000;self.n=24000;rng=np.random.default_rng(915)
        self.signals=[rng.normal(0,.07,self.n) for _ in range(3)]
        self.project=self.root/'project.json';self.plan_path=self.root/'plan.json'
        self.data={'version':1,'id':'synthetic','recording_mode':'synchronized-multitrack','tracks':[]}
        for i,x in enumerate(self.signals):
            p=self.root/f't{i}.wav';self.wav(p,x);self.data['tracks'].append({'id':f't{i}','path':p.name,'sha256':mt.digest(p),'speaker':f'Voice {i}'})
        y=sum(x*(i+1)/3 for i,x in enumerate(self.signals));p=self.root/'mix.wav'
        self.wav(p,np.column_stack([y,.8*y]));self.data['reference_mix']={'id':'mix','path':p.name,'sha256':mt.digest(p)}
        self.save_project()

    def tearDown(self):self.temp.cleanup()

    def wav(self,path,x,width=3,rate=None):
        x=np.asarray(x);x=x[:,None] if x.ndim==1 else x
        with wave.open(str(path),'wb') as f:
            f.setparams((x.shape[1],width,rate or self.rate,0,'NONE','not compressed'))
            f.writeframes(pcm.encode(x*(1<<(width*8-1)),width))

    def save_project(self):mt.write(self.project,self.data)

    def change_track(self,i,x,**kwargs):
        p=self.root/f't{i}.wav';self.wav(p,x,**kwargs);self.data['tracks'][i]['sha256']=mt.digest(p);self.save_project()

    def plan(self,edits=(),choices=None,**extra):
        choices=choices if choices is not None else {x['id']:{'choice':'delete' if x['type']=='delete' else 'adopt'} for x in edits}
        p={'version':1,'id':'v01','project_sha256':mt.digest(self.project),'edits':list(edits),
           'user_decisions':{'authority':'user','recorded_at':'synthetic-confirmation','items':choices},**extra}
        mt.write(self.plan_path,p);return p

    def cut(self,s=4000,e=6000,key='cut'):
        return {'id':key,'type':'delete','start_frame':s,'end_frame':e}

    def raw(self,path):
        with wave.open(str(path),'rb') as f:return f.readframes(f.getnframes())

    def test_independent_mix_confirms_sample_alignment(self):
        result=mt.inspect(self.project)
        self.assertEqual(result['alignment']['basis'],'independent-reference-signal')
        self.assertTrue(all(result['alignment']['per_track_signal_verified'].values()))

    def test_one_frame_difference_strongly_rejected(self):
        self.change_track(0,self.signals[0][:-1])
        with self.assertRaisesRegex(ValueError,'本 Skill 不支持'):mt.inspect(self.project)

    def test_different_rate_rejected_without_resampling(self):
        self.change_track(0,self.signals[0],rate=16000)
        with self.assertRaisesRegex(ValueError,'不同采样率'):mt.inspect(self.project)

    def test_equal_length_one_sample_offset_rejected(self):
        self.change_track(0,np.r_[0,self.signals[0][:-1]])
        with self.assertRaisesRegex(ValueError,'lag'):mt.inspect(self.project)

    def test_progressive_offset_is_rejected(self):
        x=self.signals[0].copy();x[self.n//2:]=np.r_[np.zeros(8),x[self.n//2:-8]]
        self.change_track(0,x)
        with self.assertRaisesRegex(ValueError,'未同步'):mt.inspect(self.project)

    def test_attestation_cannot_override_detected_offset(self):
        self.clock();self.change_track(0,np.roll(self.signals[0],2))
        with self.assertRaisesRegex(ValueError,'lag'):mt.inspect(self.project)

    def clock(self):
        self.data['clock_evidence']={'type':'common-sample-clock','confirmed':True,'session':'fixture','sample_zero':'recorder frame zero','reviewer':'synthetic-test'};self.save_project()

    def test_equal_length_without_independent_evidence_is_not_pass(self):
        del self.data['reference_mix'];self.save_project()
        with self.assertRaisesRegex(ValueError,'同步证据不足'):mt.inspect(self.project)

    def test_silence_not_mistaken_for_alignment(self):
        self.signals=[np.zeros(self.n) for _ in self.signals]
        for i,x in enumerate(self.signals):self.change_track(i,x)
        self.wav(self.root/'mix.wav',np.zeros((self.n,2)));self.data['reference_mix']['sha256']=mt.digest(self.root/'mix.wav');self.save_project()
        with self.assertRaisesRegex(ValueError,'同步证据不足'):mt.inspect(self.project)

    def test_explicit_clock_evidence_labelled_separately(self):
        del self.data['reference_mix'];self.clock()
        result=mt.inspect(self.project)
        self.assertEqual(result['alignment']['basis'],'explicit-common-clock-evidence')
        self.assertFalse(any(result['alignment']['per_track_signal_verified'].values()))

    def test_missing_source_hash_rejected(self):
        del self.data['tracks'][0]['sha256'];self.save_project()
        with self.assertRaisesRegex(ValueError,'source hash'):mt.inspect(self.project)

    def test_source_changed_after_user_approval_rejected(self):
        self.plan([self.cut()]);self.wav(self.root/'t0.wav',self.signals[0]*.5)
        with self.assertRaisesRegex(ValueError,'source hash'):mt.compile_plan(self.project,self.plan_path)

    def test_source_binding_changed_rejected(self):
        self.plan([self.cut()]);self.data['id']='another';self.save_project()
        with self.assertRaisesRegex(ValueError,'binding'):mt.compile_plan(self.project,self.plan_path)

    def test_unapproved_cut_not_executed(self):
        self.plan([self.cut()],{'cut':{'choice':'pending'}})
        result=mt.render(self.project,self.plan_path,self.root/'out')
        self.assertEqual(result['pending_ids'],['cut']);self.assertFalse(result['release_ready'])
        self.assertEqual(self.raw(self.root/'out/t0.wav'),self.raw(self.root/'t0.wav'))

    def test_custom_instruction_remains_non_executable(self):
        self.plan([self.cut()],{'cut':{'choice':'custom','note':'adjust inside sentence'}})
        self.assertEqual(mt.compile_plan(self.project,self.plan_path)['output_frames'],self.n)

    def test_approved_cut_shared_by_all_formats(self):
        self.change_track(1,self.signals[1],width=2)
        self.plan([self.cut()]);out=self.root/'out';result=mt.render(self.project,self.plan_path,out)
        self.assertEqual({x['frames'] for x in result['artifacts']},{self.n-2000-160})
        self.assertEqual(pcm.pcm_info(out/'t1.wav')['sample_width'],2)
        self.assertEqual(pcm.pcm_info(out/'mix.wav')['channels'],2)
        self.assertEqual(mt.verify_delivery(self.project,self.plan_path,out)['status'],'passed')

    def test_no_source_mutation_and_no_version_overwrite(self):
        hashes={p.name:mt.digest(p) for p in self.root.glob('*.wav')};self.plan([self.cut()]);out=self.root/'out'
        mt.render(self.project,self.plan_path,out)
        self.assertEqual(hashes,{p.name:mt.digest(p) for p in self.root.glob('*.wav')})
        with self.assertRaises(FileExistsError):mt.render(self.project,self.plan_path,out)

    def test_32_bit_stem_keeps_its_format_alongside_24_bit_mix(self):
        self.change_track(1,self.signals[1],width=4);self.plan([self.cut()]);out=self.root/'out'
        mt.render(self.project,self.plan_path,out)
        self.assertEqual(pcm.pcm_info(out/'t1.wav')['sample_width'],4)
        self.assertEqual(mt.verify_delivery(self.project,self.plan_path,out)['status'],'passed')

    def test_actual_join_previews_and_human_readable_mapping(self):
        self.plan([self.cut()]);out=self.root/'out';mt.render(self.project,self.plan_path,out,'tracks')
        previews=mt.load(out/'join-previews.json');self.assertEqual(len(previews['clips']),1)
        self.assertEqual(previews['clips'][0]['output_join_frame'],3840)
        self.assertTrue((out/'接点试听.html').is_file());self.assertTrue((out/'时间映射.csv').is_file())
        self.assertIn('本版输出范围',(out/'全版本处理记录.md').read_text())
        self.assertEqual(mt.verify_delivery(self.project,self.plan_path,out)['actual_join_listening'],'not_run')

    def test_prepare_refuses_a_supplied_stale_original_hash(self):
        self.data['tracks'][0]['sha256']='0'*64;self.save_project()
        with self.assertRaisesRegex(ValueError,'preparation request'):mt.prepared_project(self.project,self.root/'prepared')
        self.assertFalse((self.root/'prepared').exists())

    def test_cli_inspection_and_compile_are_usable(self):
        self.plan([self.cut()]);script=Path(mt.__file__)
        result=subprocess.run([sys.executable,str(script),'inspect',str(self.project)],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout)['frames'],self.n)
        target=self.root/'compiled.json';subprocess.run([sys.executable,str(script),'compile',str(self.project),str(self.plan_path),str(target)],check=True,capture_output=True)
        self.assertEqual(mt.load(target)['approved_ids'],['cut'])

    def test_solo_entrypoint_does_not_silently_master_one_stem(self):
        self.plan([self.cut()]);script=Path(mt.__file__).with_name('render_podcast_edl.py')
        data=mt.load(self.plan_path);data['recording_mode']='synchronized-multitrack';mt.write(self.plan_path,data)
        target=self.root/'must-not-exist.wav'
        result=subprocess.run([sys.executable,str(script),str(self.root/'t0.wav'),str(self.plan_path),str(target)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('Use multitrack.py',result.stderr);self.assertFalse(target.exists())

    def test_tampered_retained_pcm_detected(self):
        self.plan([self.cut()]);out=self.root/'out';mt.render(self.project,self.plan_path,out)
        p=out/'t0.wav';b=bytearray(p.read_bytes());b[200]^=1;p.write_bytes(b)
        with self.assertRaisesRegex(ValueError,'PCM'):mt.verify_delivery(self.project,self.plan_path,out)

    def test_tampered_fade_detected(self):
        self.plan([self.cut()]);out=self.root/'out';mt.render(self.project,self.plan_path,out)
        node=next(n for n in mt.load(out/'timeline.json')['nodes'] if n['kind']=='crossfade')
        p=out/'t0.wav';b=bytearray(p.read_bytes());b[44+node['start']*3]^=1;p.write_bytes(b)
        with self.assertRaisesRegex(ValueError,'fade'):mt.verify_delivery(self.project,self.plan_path,out)

    def test_move_keeps_whole_block_and_shared_clock(self):
        edit={'id':'move','type':'move','start_frame':4000,'end_frame':6000,'source_start_frame':4000,'source_end_frame':6000,'at_frame':10000,'block_mode':'whole'}
        self.plan([edit]);result=mt.render(self.project,self.plan_path,self.root/'out')
        self.assertEqual(result['output_frames'],self.n-3*160)
        sources=[n['source_start'] for n in mt.load(self.root/'out/timeline.json')['nodes'] if n['kind']=='copy']
        self.assertTrue(any(a>b for a,b in zip(sources,sources[1:])))

    def test_replacement_and_multiple_insertions_in_list_order(self):
        edits=[{'id':'r','type':'replace','start_frame':4000,'end_frame':6000,'source_start_frame':18000,'source_end_frame':21000,'block_mode':'whole'},
               {'id':'i','type':'insert','at_frame':4000,'source_start_frame':22000,'source_end_frame':23000,'block_mode':'whole'}]
        self.plan(edits);t=mt.compile_plan(self.project,self.plan_path)
        self.assertEqual(t['approved_ids'],['r','i']);self.assertEqual(t['output_frames'],self.n+2000-3*160)

    def test_explicit_half_second_buffers_exact_all_tracks(self):
        edits=[{'id':'ins','type':'insert','at_frame':5000,'source_start_frame':16000,'source_end_frame':18000,'block_mode':'whole','buffer_frames':4000}]
        choices={'body':{'choice':'adopt'},'ins':{'choice':'adopt'}}
        self.plan(edits,choices,base_range=[0,12000],base_range_decision_id='body')
        out=self.root/'out';result=mt.render(self.project,self.plan_path,out);t=mt.load(out/'timeline.json')
        self.assertEqual(t['output_frames'],22000);self.assertIn('body',result['approved_ids'])
        silence=[n for n in t['nodes'] if n['kind']=='silence'];self.assertEqual([n['end']-n['start'] for n in silence],[4000,4000])
        for f in out.glob('*.wav'):
            with wave.open(str(f),'rb') as w:
                for n in silence:w.setpos(n['start']);self.assertEqual(set(w.readframes(4000)),{0})

    def test_buffers_default_to_zero_not_project_specific_half_second(self):
        edit={'id':'ins','type':'insert','at_frame':5000,'source_start_frame':16000,'source_end_frame':18000,'block_mode':'whole'}
        self.plan([edit]);self.assertFalse(any(n['kind']=='silence' for n in mt.compile_plan(self.project,self.plan_path)['nodes']))

    def test_workspace_trim_requires_explicit_decision(self):
        self.plan(base_range=[0,12000])
        with self.assertRaisesRegex(ValueError,'own user decision'):mt.compile_plan(self.project,self.plan_path)

    def test_keep_cannot_be_overridden_by_overlapping_delete(self):
        edits=[self.cut(key='keep'),self.cut(5000,7000,'delete')]
        self.plan(edits,{'keep':{'choice':'keep'},'delete':{'choice':'delete'}})
        with self.assertRaisesRegex(ValueError,'keep decision'):mt.compile_plan(self.project,self.plan_path)

    def test_overlapping_replacements_require_combined_decision(self):
        self.plan([self.cut(),self.cut(5000,7000,'another')])
        with self.assertRaisesRegex(ValueError,'Overlapping'):mt.compile_plan(self.project,self.plan_path)

    def test_non_integer_frames_rejected(self):
        self.plan([self.cut(4000.1,6000)])
        with self.assertRaisesRegex(ValueError,'integer'):mt.compile_plan(self.project,self.plan_path)

    def test_whole_or_fine_mode_must_be_explicit(self):
        self.plan([{'id':'i','type':'insert','at_frame':5000,'source_start_frame':16000,'source_end_frame':18000}])
        with self.assertRaisesRegex(ValueError,'whole-block'):mt.compile_plan(self.project,self.plan_path)

    def test_no_mix_generates_labelled_proxy_only_with_clock_evidence(self):
        del self.data['reference_mix'];self.clock();self.plan([self.cut()]);out=self.root/'out'
        result=mt.render(self.project,self.plan_path,out)
        self.assertEqual(len(result['artifacts']),4)
        self.assertTrue(result['artifacts'][-1]['generated_analysis_mix'])
        self.assertFalse((out/'analysis-source.wav').exists())
        self.assertEqual(mt.verify_delivery(self.project,self.plan_path,out)['status'],'passed')

    def test_mix_preview_and_tracks_use_identical_map(self):
        self.plan([self.cut()]);mt.render(self.project,self.plan_path,self.root/'preview','mix');mt.render(self.project,self.plan_path,self.root/'stems','tracks')
        self.assertEqual(mt.load(self.root/'preview/timeline.json'),mt.load(self.root/'stems/timeline.json'))

    def transcript(self):
        return {'project_sha256':mt.digest(self.project),'sentences':[{'id':'a','speaker':'Voice A','start_frame':3000,'end_frame':7000,'text':'before removed after',
                'words':[{'start_frame':3000,'end_frame':3900,'text':'before '},{'start_frame':4200,'end_frame':5800,'text':'removed '},{'start_frame':6200,'end_frame':7000,'text':'after'}]}]}

    def test_projection_removes_cut_words_without_fade_duplication(self):
        self.plan([self.cut()]);t=mt.compile_plan(self.project,self.plan_path);r=mt.transcript_projection(self.transcript(),t)
        self.assertEqual(''.join(x['text'] for x in r['sentences']),'before after')
        self.assertEqual([x['speaker'] for x in r['sentences']],['Voice A','Voice A'])
        self.assertEqual(r['actual_output_asr'],'not_run')

    def test_partial_sentence_without_words_not_fabricated(self):
        self.plan([self.cut()]);tr=self.transcript();del tr['sentences'][0]['words']
        with self.assertRaisesRegex(ValueError,'without word timings'):mt.transcript_projection(tr,mt.compile_plan(self.project,self.plan_path))

    def test_zero_duration_evidence_not_given_invented_duration(self):
        self.plan();tr={'project_sha256':mt.digest(self.project),'sentences':[{'id':'zero','start_frame':2000,'end_frame':2000,'text':'unknown'}]}
        r=mt.transcript_projection(tr,mt.compile_plan(self.project,self.plan_path));self.assertFalse(r['sentences']);self.assertEqual(len(r['timing_issues']),1)

    def test_history_preserves_keep_delete_and_parent_binding(self):
        self.plan([self.cut()],{'cut':{'choice':'keep'}});first=self.root/'v1';mt.render(self.project,self.plan_path,first)
        self.plan([self.cut()],id='v02',revised_ids=['cut'],parent_record='v1/version-record.json',parent_record_sha256=mt.digest(first/'version-record.json'))
        mt.render(self.project,self.plan_path,self.root/'v2');text=(self.root/'v2/全版本处理记录.md').read_text()
        self.assertIn('|cut|keep|未执行，保留|',text);self.assertIn('|cut|delete|已执行|',text)
        record=mt.load(first/'version-record.json');record['version']='tampered';mt.write(first/'version-record.json',record)
        with self.assertRaisesRegex(ValueError,'parent record hash'):mt.render(self.project,self.plan_path,self.root/'v3')

    def test_revision_cannot_silently_restore_an_earlier_cut(self):
        self.plan([self.cut()]);first=self.root/'v1';mt.render(self.project,self.plan_path,first)
        self.plan([],id='v02',parent_record='v1/version-record.json',parent_record_sha256=mt.digest(first/'version-record.json'))
        with self.assertRaisesRegex(ValueError,'omitted an earlier'):mt.render(self.project,self.plan_path,self.root/'v2')

    def test_revision_cannot_silently_override_manual_keep(self):
        self.plan([self.cut()],{'cut':{'choice':'keep'}});first=self.root/'v1';mt.render(self.project,self.plan_path,first)
        self.plan([self.cut()],id='v02',parent_record='v1/version-record.json',parent_record_sha256=mt.digest(first/'version-record.json'))
        with self.assertRaisesRegex(ValueError,'revised_ids'):mt.render(self.project,self.plan_path,self.root/'v2')

    def test_revision_cannot_silently_restore_workspace(self):
        self.plan(choices={'body':{'choice':'adopt'}},base_range=[0,12000],base_range_decision_id='body')
        first=self.root/'v1';mt.render(self.project,self.plan_path,first)
        self.plan(choices={'body':{'choice':'adopt'}},id='v02',base_range_decision_id='body',parent_record='v1/version-record.json',parent_record_sha256=mt.digest(first/'version-record.json'))
        with self.assertRaisesRegex(ValueError,'workspace boundary'):mt.render(self.project,self.plan_path,self.root/'v2')

    def review_fixture(self,operation=None):
        operation=operation or self.cut();spec={'version':'review1','items':[{'id':operation['id'],'start_ms':500,'end_ms':750,'text':'synthetic candidate','suggestion':'uncertain','proposed_decision':'delete' if operation['type']=='delete' else 'adopt','operation':operation}]}
        sp=self.root/'review-spec.json';mt.write(sp,spec);out=self.root/'review'
        with contextlib.redirect_stdout(io.StringIO()):mt.build_review(self.project,sp,out)
        return review.Store(out),operation

    def accept(self,store,choice):
        state=store.read();key=next(iter(state['items']));value={**state['items'][key],'decision':choice}
        return store.apply({'binding':store.binding,'base_revision':state['revision'],'operation':'item','changes':{key:value}})

    def test_durable_review_decision_drives_compiler(self):
        store,operation=self.review_fixture();self.accept(store,'delete')
        p=self.plan([operation]);p.pop('user_decisions');p['review_directory']='review';mt.write(self.plan_path,p)
        self.assertEqual(mt.compile_plan(self.project,self.plan_path)['approved_ids'],['cut'])
        self.assertEqual(review.Store(store.root).read()['items']['cut']['decision'],'delete')

    def test_review_withdrawal_during_render_cannot_publish_old_choice(self):
        store,op=self.review_fixture();self.accept(store,'delete')
        plan=self.plan([op]);plan.pop('user_decisions');plan['review_directory']='review';mt.write(self.plan_path,plan)
        real=mt.write_track;changed=[]
        def write_and_withdraw(*args):
            real(*args)
            if not changed:self.accept(store,'keep');changed.append(True)
        with mock.patch.object(mt,'write_track',side_effect=write_and_withdraw):
            with self.assertRaisesRegex(ValueError,'review changed during render'):mt.render(self.project,self.plan_path,self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_review_binds_even_quiet_unmodified_reference_stems(self):
        store,_=self.review_fixture();self.wav(self.root/'t0.wav',self.signals[0]*.9)
        with self.assertRaisesRegex(ValueError,'stem changed'):review.Store(store.root)

    def test_review_operation_cannot_be_changed_after_adoption(self):
        store,operation=self.review_fixture();self.accept(store,'delete');p=self.plan([self.cut(3000,6000)]);p.pop('user_decisions');p['review_directory']='review';mt.write(self.plan_path,p)
        with self.assertRaisesRegex(ValueError,'Operation changed'):mt.compile_plan(self.project,self.plan_path)

    def test_move_review_uses_adopt_not_delete(self):
        op={'id':'move','type':'move','start_frame':4000,'end_frame':6000,'source_start_frame':4000,'source_end_frame':6000,'at_frame':10000,'block_mode':'whole'}
        store,_=self.review_fixture(op)
        with self.assertRaisesRegex(ValueError,'Use adopt'):self.accept(store,'delete')
        self.accept(store,'adopt');p=self.plan([op]);p.pop('user_decisions');p['review_directory']='review';mt.write(self.plan_path,p)
        self.assertEqual(mt.compile_plan(self.project,self.plan_path)['approved_ids'],['move'])

    def test_preparation_binds_decoded_count_and_originals(self):
        p=mt.prepared_project(self.project,self.root/'prepared');r=mt.inspect(p)
        self.assertEqual(r['frames'],self.n);self.assertTrue(mt.load(p)['tracks'][0]['original_sha256'])

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_lossy_prepare_retains_native_rate_and_rejects_count_difference(self):
        mp3=self.root/'source.mp3';subprocess.run(['ffmpeg','-v','error','-i',str(self.root/'t0.wav'),str(mp3)],check=True)
        self.data.pop('reference_mix');self.data['tracks']=[{'id':f'p{i}','path':mp3.name if i==0 else 'source-copy.mp3'} for i in range(2)]
        shutil.copy2(mp3,self.root/'source-copy.mp3');self.clock()
        p=mt.prepared_project(self.project,self.root/'lossy');self.assertEqual(mt.inspect(p)['sample_rate'],self.rate)
        self.data['tracks'][1]['path']='t1.wav';self.change_track(1,self.signals[1][:-10])
        with self.assertRaisesRegex(ValueError,'不同长度'):mt.prepared_project(self.project,self.root/'unsupported')
        self.assertFalse((self.root/'unsupported').exists())


if __name__=='__main__':unittest.main()
