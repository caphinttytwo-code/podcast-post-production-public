"""Behavioral integration checks: cache/paths, source integrity and branch isolation."""
import importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from shared.guards import guard_path,guard_directory
from shared.test_steps import Steps,ControlFailed,protection_result
from shared import environment,setup

def load(name):
 path=ROOT/'modules/audio-edit/scripts'/name;spec=importlib.util.spec_from_file_location('rc63_'+path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class BranchTests(unittest.TestCase):
 def test_missing_review_does_not_stop_independent_action_and_retains_hashes(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);source=root/'source';source.write_bytes(b'fixture');s=Steps(root/'evidence');s.protect(source)
   with patch('shared.environment.inspect',return_value={'ok':False,'missing':['filter:drawtext']}):s.run('review',feature='trailers:review',action=lambda _:self.fail('must not execute'))
   s.run('unavailable',needs=[root/'missing'],after=['review'],action=lambda _:self.fail('missing input'))
   s.run('independent',action=lambda _:True);report=s.save()
   self.assertEqual([x['status'] for x in s.rows],['BLOCKED','NOT RUN','PASS']);self.assertEqual(report['protected_input_sha256_before'],report['protected_input_sha256_final'])
 def test_source_mutation_stops_batch_without_replacing_before_hash(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);source=root/'source';source.write_bytes(b'original');s=Steps(root/'evidence');s.protect(source);before=dict(s.protected)
   s.run('mutation',action=lambda _:source.write_bytes(b'changed!'));s.protect(source);s.run('later',action=lambda _:self.fail('must stop'))
   report=s.save();self.assertEqual([x['status'] for x in s.rows],['FAIL','NOT RUN']);self.assertEqual(s.protected,before);self.assertFalse(report['protected_inputs_unchanged'])
 def test_normal_control_must_satisfy_output_assertions_before_negative_cases(self):
  with self.assertRaises(ControlFailed):protection_result('render normal output control','FAIL',exit_code=0,positive_output_exists=False)
  self.assertEqual(protection_result('render normal output control','PASS',exit_code=0,positive_output_exists=True)['status'],'PASS')
 def test_executed_assertion_is_fail_and_later_action_runs(self):
  with tempfile.TemporaryDirectory() as td:
   s=Steps(Path(td)/'evidence');s.run('failure',action=lambda _:(_ for _ in ()).throw(AssertionError('expected failed assertion')));s.run('independent',action=lambda _:True)
   self.assertEqual([x['status'] for x in s.rows],['FAIL','PASS'])
 def test_low_version_not_run_as_production_pass(self):
  def info(value,kind):return {'path':sys.executable,'version':'8.1.0','sha256':'test','version_output':'test'}
  with patch('shared.environment.tool_info',side_effect=info),patch('shared.environment.names',return_value={'libmp3lame','pcm_s24le','flac','atrim','asetpts','concat','loudnorm','afade'}),patch('shared.environment.smoke',side_effect=AssertionError('unsupported production executed')):
   report=environment.inspect('audio-edit',feature='basic',smoke_dir='/not-used')
  self.assertEqual(report['status'],'BLOCKED');self.assertIn('ffmpeg>=8.1.1',report['missing']);self.assertEqual(report['checks'][-1]['status'],'NOT RUN')
 def test_multitrack_not_covered_by_solo_full(self):
  rows=[{'id':'audio-edit:synchronized-multitrack','status':'PASS'},{'id':'audio-edit:basic','status':'PASS'}]
  groups=[{'group':'synthetic','status':'PASS','items':[{'case':'solo','feature':'audio-edit:basic','status':'PASS'}]}];setup.apply_validation_scope(rows,groups)
  self.assertEqual(rows[0]['full_automatic_status'],'NOT RUN');self.assertEqual(rows[0]['validation_scope'],'smoke');self.assertEqual(rows[1]['full_automatic_status'],'PASS')
 def test_unrelated_review_block_preserves_audio_full_evidence(self):
  rows=[{'id':'audio-edit:basic','status':'PASS'}];setup.apply_validation_scope(rows,[{'group':'synthetic','items':[{'step':'audio','feature':'audio-edit:basic','status':'PASS'},{'step':'review','feature':'trailers:review','status':'BLOCKED'}]}])
  self.assertEqual(rows[0]['status'],'PASS');self.assertEqual(rows[0]['validation_scope'],'full_automatic')
 def test_three_new_features_keep_distinct_requirements(self):
  self.assertEqual(environment.profile('audio-edit','paragraph-review')[1],['ffprobe']);self.assertEqual(environment.profile('audio-edit','preserve-source')[1],[]);self.assertIn('numpy',environment.profile('audio-edit','synchronized-multitrack')[0])
 def test_role_service_does_not_read_secrets_or_call_model(self):
  with patch('urllib.request.urlopen',side_effect=AssertionError('network')),patch('subprocess.check_output',side_effect=AssertionError('secret')):
   s=setup.external_services()
  self.assertEqual(s['new_role_transcription']['price'],'UNKNOWN');self.assertEqual(s['model_calls'],0);self.assertFalse(s['multitrack_local']['model_api_fee'])

class BoundaryTests(unittest.TestCase):
 def test_guard_positive_then_entire_package_rejection(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'normal';self.assertEqual(guard_path(p),p)
   with self.assertRaises(ValueError):guard_path(ROOT/'references/unsafe.json')
 def test_guard_positive_then_hardlink_rejection(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);p=root/'original';p.write_bytes(b'original');normal=root/'normal';guard_path(normal,p);alias=root/'alias';os.link(p,alias)
   with self.assertRaises(ValueError):guard_path(alias)
   self.assertEqual(p.read_bytes(),b'original')
 def test_guard_positive_then_symlink_parent_rejection(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);real=root/'real';real.mkdir();guard_path(real/'normal');link=root/'link'
   try:link.symlink_to(real,target_is_directory=True)
   except OSError as exc:
    if getattr(exc,'winerror',None)==1314:raise RuntimeError('BLOCKED: Windows symlink permission') from exc
    raise
   with self.assertRaises(ValueError):guard_path(link/'child')
   self.assertEqual(list(real.iterdir()),[])
 def test_derived_temp_cannot_alias_input(self):
  m=load('review.py')
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);m.atomic(root/'normal.json',{'normal':True});victim=root/'victim';victim.write_bytes(b'original');os.link(victim,root/'state.json.tmp')
   with self.assertRaises(ValueError):m.atomic(root/'state.json',{'unsafe':True})
   self.assertEqual(victim.read_bytes(),b'original');self.assertFalse((root/'state.json').exists())
 def test_same_size_mtime_source_tamper_cannot_save_review(self):
  m=load('review.py')
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);audio=root/'audio.wav';audio.write_bytes(b'original');spec=root/'spec.json';spec.write_text(json.dumps({'source_audio':'audio.wav','items':[{'id':'a','start_ms':0,'end_ms':500,'text':'fixture','suggestion':'uncertain'}]}))
   with patch.object(m,'probe_duration',return_value=1000):m.build(spec,root/'review')
   store=m.Store(root/'review');state=store.read();body={'binding':store.binding,'base_revision':0,'operation':'item','changes':{'a':{'decision':'keep','text_correction':'','note':'synthetic'}}};saved,_=store.apply(body);self.assertEqual(saved['revision'],1)
   stat=audio.stat();audio.write_bytes(b'changed!');os.utime(audio,ns=(stat.st_atime_ns,stat.st_mtime_ns));before=(root/'review/state.json').read_bytes();body.update(base_revision=1);body['changes']['a']['decision']='delete'
   with self.assertRaisesRegex(ValueError,'changed'):store.apply(body)
   self.assertEqual((root/'review/state.json').read_bytes(),before)
if __name__=='__main__':unittest.main()
