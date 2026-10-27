import contextlib
import copy
import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import review


class ParagraphReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        source=self.root/'source.wav'
        with wave.open(str(source),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*160000)
        self.spec={'source_audio':'source.wav','version':'v01','items':[
            {'id':'S1','start_ms':100,'end_ms':900,'text':'保留的上下文。','suggestion':'keep'},
            {'id':'S2','start_ms':1500,'end_ms':2000,'text':'失败起句。','suggestion':'uncertain','proposed_decision':'delete','repeat_group_ids':['R1']},
            {'id':'S3','start_ms':2100,'end_ms':3000,'text':'最后完整说法。','suggestion':'uncertain','proposed_decision':'keep','repeat_group_ids':['R1']},
            {'id':'S4','start_ms':3500,'end_ms':4000,'text':'另一个上下文。','suggestion':'keep'},
            {'id':'S5','start_ms':7000,'end_ms':7500,'text':'含否定的疑点。','suggestion':'uncertain'},
            {'id':'S6','start_ms':8000,'end_ms':8500,'text':'明确失败片段。','suggestion':'delete'}]}
        self.path=self.root/'spec.json';self.path.write_text(json.dumps(self.spec))
        self.output=self.root/'review'
        with contextlib.redirect_stdout(io.StringIO()):self.data=review.build(self.path,self.output)
        self.store=review.Store(self.output);self.initial=self.store.read()
    def tearDown(self):self.tmp.cleanup()
    def body(self,changes,base=0,operation='item',**extra):return {'binding':self.data['binding'],'base_revision':base,'operation':operation,'changes':changes,**extra}
    def record(self,id,decision,**extra):return {**self.initial['items'][id],'decision':decision,**extra}
    def apply(self,id,decision,base=0,**fields):return self.store.apply(self.body({id:self.record(id,decision,**fields)},base))
    def test_repeat_group_is_one_card_context_is_not_a_target(self):
        self.assertEqual(len(self.data['cards']),2);c=self.data['cards'][0]
        self.assertEqual(c['target_ids'],['S2','S3']);self.assertIn('S1',c['context_ids']);self.assertEqual(c['proposal'],{'S2':'delete','S3':'keep'})
        self.assertTrue(all(r['decision']=='pending' for r in self.initial['items'].values()))
    def test_card_cannot_mutate_context_or_fake_proposal(self):
        c=self.data['cards'][0]
        with self.assertRaises(ValueError):self.store.apply(self.body({'S1':self.record('S1','delete')},operation='card',card_id=c['id'],action='delete'))
        with self.assertRaises(ValueError):self.store.apply(self.body({i:self.record(i,'delete') for i in c['target_ids']},operation='card',card_id=c['id'],action='proposal'))
    def test_card_proposal_and_custom_note_preserve_other_rows(self):
        c=self.data['cards'][0];changes={i:self.record(i,v) for i,v in c['proposal'].items()}
        state,conflicts=self.store.apply(self.body(changes,operation='card',card_id=c['id'],action='proposal'))
        self.assertFalse(conflicts);self.assertEqual(state['items']['S1'],self.initial['items']['S1'])
        state,_=self.store.apply(self.body({'S5':self.record('S5','uncertain',note='保留理由待方案落实')},base=1,operation='card',card_id='C002',action='custom'))
        self.assertEqual(state['items']['S5']['decision'],'uncertain')
    def test_three_way_disjoint_updates_merge_and_same_field_conflicts(self):
        self.apply('S1','keep')
        state,conflicts=self.apply('S6','delete',base=0)
        self.assertFalse(conflicts);self.assertEqual(state['items']['S1']['decision'],'keep')
        state,conflicts=self.apply('S1','delete',base=0)
        self.assertIsNone(state);self.assertEqual(conflicts,{'S1':['decision']});self.assertEqual(self.store.read()['revision'],2)
    def test_correction_and_audio_decision_merge_independently(self):
        self.apply('S1','keep')
        state,conflicts=self.apply('S1','pending',base=0,text_correction='仅修正字形')
        self.assertFalse(conflicts);self.assertEqual(state['items']['S1'],{'decision':'keep','text_correction':'仅修正字形','note':''})
    def test_server_does_not_trust_forged_client_base(self):
        self.apply('S1','keep');body=self.body({'S1':self.record('S1','delete')},base=0)
        body['base']={'items':{'S1':self.record('S1','keep')}}
        state,conflicts=self.store.apply(body);self.assertIsNone(state);self.assertIn('S1',conflicts)
    def test_bulk_needs_exact_authorization_and_preserves_manual_choice(self):
        with self.assertRaises(ValueError):self.store.apply(self.body({'S1':self.record('S1','keep')},operation='bulk'))
        self.apply('S1','delete');before=self.store.read()
        ids=['S4','S6'];changes={i:self.record(i,self.store.by[i]['suggestion']) for i in ids}
        state,_=self.store.apply(self.body(changes,base=1,operation='bulk',authorization={'intent':'adopt-definite-suggestions','ids':ids}))
        self.assertEqual(state['items']['S1'],before['items']['S1']);self.assertEqual(state['items']['S2']['decision'],'pending')
        with self.assertRaises(ValueError):self.store.apply(self.body({'S1':self.record('S1','keep')},base=2,operation='bulk',authorization={'intent':'adopt-definite-suggestions','ids':['S1']}))
    def test_restart_restores_saved_state_history_and_base_snapshot(self):
        self.apply('S1','keep');fresh=review.Store(self.output)
        self.assertEqual(fresh.read()['revision'],1);self.assertEqual(json.loads((self.output/'backups/r000000.json').read_text())['revision'],0)
        self.assertEqual(len((self.output/'history.jsonl').read_text().splitlines()),1)
    def test_wrong_version_import_and_data_tampering_are_rejected(self):
        b=self.body({'S1':self.record('S1','keep')});b['binding']={}
        with self.assertRaises(ValueError):self.store.apply(b)
        data=json.loads((self.output/'data.json').read_text());data['items'][0]['text']='其他素材';review.atomic(self.output/'data.json',data)
        with self.assertRaisesRegex(ValueError,'changed'):review.Store(self.output)
    def test_changed_media_blocks_save(self):
        p=self.root/'source.wav';p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'media changed'):self.apply('S1','keep')
    def test_reviewed_directory_cannot_be_regenerated_and_unknown_time_not_guessed(self):
        with self.assertRaises(ValueError):review.build(self.path,self.output)
        self.spec['items'][1]['end_ms']=1500;self.path.write_text(json.dumps(self.spec))
        with self.assertRaisesRegex(ValueError,'timestamps'):review.build(self.path,self.root/'other')
        self.assertFalse((self.root/'other').exists())
    def test_bound_backup_can_restore_empty_project_but_not_overwrite_new_manual_work(self):
        changes={'S1':self.record('S1','keep')}
        body=self.body(changes,base=9,operation='import',authorization={'intent':'restore-backup','ids':['S1']})
        state,conflicts=self.store.apply(body)
        self.assertFalse(conflicts);self.assertEqual(state['items']['S1']['decision'],'keep')
        with self.assertRaisesRegex(ValueError,'revision'):self.store.apply(body)
    def test_independent_store_instances_share_atomic_revision_base(self):
        other=review.Store(self.output)
        self.apply('S1','keep')
        state,conflicts=other.apply(self.body({'S6':self.record('S6','delete')},base=0))
        self.assertFalse(conflicts);self.assertEqual(state['revision'],2);self.assertEqual(state['items']['S1']['decision'],'keep')
    def test_http_save_range_health_and_origin(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),review.handler(self.store));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertEqual(json.load(urllib.request.urlopen(url+'/health'))['binding'],self.data['binding'])
            r=urllib.request.urlopen(urllib.request.Request(url+'/audio',headers={'Range':'bytes=44-63'}));self.assertEqual(r.status,206);self.assertEqual(len(r.read()),20)
            body=review.canonical(self.body({'S1':self.record('S1','keep')}))
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(url+'/progress',data=body,headers={'Origin':'https://example.invalid'}))
            self.assertEqual(e.exception.code,403)
            r=urllib.request.urlopen(urllib.request.Request(url+'/progress',data=body,headers={'Origin':url}));self.assertEqual(json.load(r)['revision'],1)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
