"""Version-bound paragraph review, durable local saves and three-way merging."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, package_root
from shared.guards import guard_path, guard_directory

import argparse
import copy
import contextlib
import datetime
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DECISIONS = {'pending','keep','delete','uncertain','adopt'}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic(path,value):
    path=guard_path(path)
    tmp=guard_path(path.with_suffix(path.suffix+'.tmp'))
    with tmp.open('wb') as f:
        f.write(canonical(value));f.flush();os.fsync(f.fileno())
    tmp.replace(path)


def probe_duration(path):
    return round(float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration',
                                               '-of','csv=p=0',str(path)],text=True))*1000)


def build(spec_path,output):
    guard_directory(output, spec_path)
    spec_path=Path(spec_path).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Use a new version directory; never rebuild reviewed data')
    if output.is_relative_to(Path(__file__).resolve().parents[1]):raise ValueError('Keep project data outside the Skill repository')
    spec=json.loads(spec_path.read_text())
    multitrack=spec.get('multitrack_project')
    source=(spec_path.parent/spec['source_audio']).resolve()
    audio=(spec_path.parent/spec.get('playback_audio',spec['source_audio'])).resolve()
    duration=probe_duration(source)
    if abs(probe_duration(audio)-duration)>100:raise ValueError('Playback proxy does not preserve source duration')
    manuscript=(spec_path.parent/spec['manuscript']).resolve() if spec.get('manuscript') else None
    items=copy.deepcopy(spec['items']);by={x['id']:x for x in items}
    if any(not isinstance(i,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',i) for i in by):raise ValueError('Invalid review ID')
    if not items or len(by)!=len(items):raise ValueError('Empty or duplicate review IDs')
    last=0
    for x in items:
        s,e=x.get('start_ms'),x.get('end_ms')
        if type(s) is not int or type(e) is not int or not last<=s<e<=duration:
            raise ValueError('Review needs real, ordered, positive source timestamps; isolate unknown timing first')
        if not isinstance(x.get('text'),str) or x.get('suggestion') not in {'keep','delete','uncertain'}:
            raise ValueError('Invalid text or suggestion')
        if x.get('proposed_decision') not in ({None,'keep','delete','adopt'} if multitrack else {None,'keep','delete'}):raise ValueError('Invalid proposed decision')
        if x.get('proposed_decision')=='adopt' and not isinstance(x.get('operation'),dict):raise ValueError('Adopt requires a bound operation')
        last=e
    # Connected repeat groups keep intersecting retakes in one card, never duplicate targets.
    components=[]
    for x in items:
        groups=set(x.get('repeat_group_ids',[]))
        if not groups:continue
        matching=[c for c in components if c['groups']&groups]
        merged={'groups':set(groups),'ids':{x['id']}}
        for c in matching:merged['groups']|=c['groups'];merged['ids']|=c['ids'];components.remove(c)
        components.append(merged)
    grouped={i for c in components for i in c['ids']}
    components += [{'groups':set(),'ids':{x['id']}} for x in items if x['id'] not in grouped and x['suggestion']=='uncertain']
    cards=[]
    for c in sorted(components,key=lambda c:min(by[i]['start_ms'] for i in c['ids'])):
        targets=[x['id'] for x in items if x['id'] in c['ids'] and x['suggestion']=='uncertain']
        if not targets:continue
        start=max(0,min(by[i]['start_ms'] for i in c['ids'])-5000)
        end=min(duration,max(by[i]['end_ms'] for i in c['ids'])+5000)
        proposal={i:by[i]['proposed_decision'] for i in targets if by[i].get('proposed_decision')}
        takes=[]
        for group in spec.get('repeat_groups',[]):
            if group['id'] in c['groups']:
                for take in group.get('takes',[]):
                    if not 0<=take['start_ms']<take['end_ms']<=duration:raise ValueError('Invalid retake timing')
                    takes.append(take)
        cards.append({'id':f'C{len(cards)+1:03}','target_ids':targets,
                      'context_ids':[x['id'] for x in items if x['end_ms']>start and x['start_ms']<end],
                      'start_ms':start,'end_ms':end,'proposal':proposal if len(proposal)==len(targets) else {},
                      'takes':takes,'title':by[targets[0]].get('chapter','整段确认')})
    data={'version':spec.get('version','v01'),'duration_ms':duration,'items':items,'cards':cards}
    bound_media=[]
    if multitrack:
        multitrack=(spec_path.parent/multitrack).resolve()
        data['recording_mode']='synchronized-multitrack'
        rate=spec.get('multitrack_sample_rate')
        if type(rate) is not int or rate<=0:raise ValueError('Multitrack review requires its actual sample rate')
        with wave.open(str(source),'rb') as pcm_source:
            if pcm_source.getframerate()!=rate:raise ValueError('Review timebase differs from source sample rate')
        data['sample_rate']=rate
        for item in spec.get('bound_media',[]):
            p=(spec_path.parent/item['path']).resolve()
            bound_media.append({'id':item['id'],'path':str(p),'sha256':digest(p)})
        if not bound_media:raise ValueError('Multitrack review must bind its media')
    binding={'source_sha256':digest(source),'audio_sha256':digest(audio),
             'manuscript_sha256':digest(manuscript) if manuscript else None,
             'data_sha256':hashlib.sha256(canonical(data)).hexdigest()}
    if multitrack:
        binding.update(multitrack_project_sha256=digest(multitrack),bound_media_sha256=hashlib.sha256(canonical(bound_media)).hexdigest())
    data['binding']=binding
    output.mkdir(parents=True)
    atomic(output/'data.json',data)
    atomic(output/'manifest.json',{'binding':binding,'source':str(source),'audio':str(audio),
                                  'manuscript':str(manuscript) if manuscript else None,
                                  **({'multitrack_project':str(multitrack),'bound_media':bound_media} if multitrack else {})})
    atomic(output/'state.json',{'binding':binding,'revision':0,'items':{
        x['id']:{'decision':'pending','text_correction':'','note':''} for x in items},'updated_at':now()})
    (output/'backups').mkdir()
    print(str(output))
    return data


def validate_record(r):
    if not isinstance(r,dict) or set(r)!={'decision','text_correction','note'} or r.get('decision') not in DECISIONS:
        raise ValueError('Invalid decision record')
    if any(not isinstance(r[k],str) or len(r[k])>12000 for k in ('text_correction','note')):
        raise ValueError('Invalid correction or note')


def merge_items(base,server,changes):
    result=copy.deepcopy(server);conflicts={}
    for key,value in changes.items():
        if key not in base or key not in server:raise ValueError('Unknown or missing base ID')
        validate_record(base[key]);validate_record(value)
        merged={}
        for field in ('decision','text_correction','note'):
            old,current,new=base[key][field],server[key][field],value[field]
            if current!=old and new!=old and current!=new:
                conflicts.setdefault(key,[]).append(field)
            merged[field]=current if new==old else new
        result[key]=merged
    return result,conflicts


@contextlib.contextmanager
def transaction_lock(root):
    guard_directory(root)
    with guard_path(root/'.state.lock').open('a+b') as f:
        if os.name=='nt':
            import msvcrt
            f.seek(0,2)
            if f.tell()==0:f.write(b'0');f.flush()
            f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)


class Store:
    def __init__(self,root):
        guard_directory(root)
        self.root=Path(root).resolve();self.lock=threading.Lock()
        self.data=json.loads((self.root/'data.json').read_text());self.manifest=json.loads((self.root/'manifest.json').read_text())
        self.binding=self.data['binding'];self.by={x['id']:x for x in self.data['items']}
        plain={k:v for k,v in self.data.items() if k!='binding'}
        if hashlib.sha256(canonical(plain)).hexdigest()!=self.binding['data_sha256']:
            raise ValueError('Review data changed after binding')
        if self.manifest['binding']!=self.binding:raise ValueError('Manifest binding differs')
        self.verify_media()
        with self.lock:self.read()

    def verify_media(self):
        signatures={}
        if 'multitrack_project_sha256' in self.binding:
            if digest(self.manifest['multitrack_project'])!=self.binding['multitrack_project_sha256']:raise ValueError('Bound multitrack project changed')
            if hashlib.sha256(canonical(self.manifest.get('bound_media',[]))).hexdigest()!=self.binding['bound_media_sha256']:raise ValueError('Bound stem list changed')
            for item in self.manifest['bound_media']:
                stat=Path(item['path']).stat();signature=(stat.st_size,stat.st_mtime_ns)
                key='stem:'+item['id']
                if digest(item['path'])!=item['sha256']:raise ValueError('Bound stem changed')
                signatures[key]=signature
        for role,key in [('source','source_sha256'),('audio','audio_sha256'),('manuscript','manuscript_sha256')]:
            path=self.manifest.get(role)
            if path:
                stat=Path(path).stat();signature=(stat.st_size,stat.st_mtime_ns)
                if digest(path)!=self.binding[key]:raise ValueError('Bound media changed')
                signatures[role]=signature
        self.media_signatures=signatures

    def read(self):
        state=json.loads((self.root/'state.json').read_text())
        if state.get('binding')!=self.binding or set(state.get('items',{}))!=set(self.by):raise ValueError('State binding or IDs differ')
        for key,value in state['items'].items():
            validate_record(value)
            self.validate_operation_choice(key,value)
        return state

    def validate_operation_choice(self,key,value):
        operation=self.by[key].get('operation')
        if value['decision']=='adopt' and (not self.binding.get('multitrack_project_sha256') or not isinstance(operation,dict)):
            raise ValueError('Adopt is only valid for a bound multitrack operation')
        if value['decision']=='delete' and self.binding.get('multitrack_project_sha256') and isinstance(operation,dict) and operation.get('type')!='delete':
            raise ValueError('Use adopt to approve an insertion, replacement or move')

    def apply(self,body):
        guard_directory(self.root, self.manifest.get("source"), self.manifest.get("audio"), self.manifest.get("manuscript"))
        with self.lock, transaction_lock(self.root):
            self.verify_media()
            if body.get('binding')!=self.binding:raise ValueError('Wrong review version')
            if type(body.get('base_revision')) is not int:raise ValueError('Missing base revision')
            old=self.read(); revision=body['base_revision']
            if revision<0:raise ValueError('Invalid revision')
            fresh_restore = body.get('operation')=='import' and old['revision']==0 and all(v['decision']=='pending' and not v['note'] and not v['text_correction'] for v in old['items'].values())
            if revision>old['revision'] and not fresh_restore:raise ValueError('Invalid revision')
            # An explicitly imported bound backup may fill an empty project, never replace manual work.
            path=self.root/'backups'/f'r{revision:06}.json'
            base=old if revision==old['revision'] or fresh_restore else json.loads(path.read_text())
            changes=body.get('changes')
            if not isinstance(changes,dict) or not changes or not set(changes)<=set(self.by):raise ValueError('Invalid changes')
            for key,value in changes.items():
                validate_record(value)
                self.validate_operation_choice(key,value)
            operation=body.get('operation')
            if operation=='card':
                card=next((c for c in self.data['cards'] if c['id']==body.get('card_id')),None)
                if not card or set(changes)!=set(card['target_ids']):raise ValueError('Card may only update its targets')
                action=body.get('action')
                if action in {'keep','delete','pending','uncertain'}:expected={i:action for i in changes}
                elif action=='proposal' and card['proposal']:expected=card['proposal']
                elif action=='custom':
                    if any(not v.get('note','').strip() for v in changes.values()):raise ValueError('Custom instructions require notes')
                    expected={i:'uncertain' for i in changes}
                else:raise ValueError('Invalid card action')
                if any(v.get('decision')!=expected[i] for i,v in changes.items()):raise ValueError('Card decisions differ from action')
            elif operation=='bulk':
                auth=body.get('authorization',{})
                if not isinstance(auth,dict):raise ValueError('Invalid authorization')
                if auth.get('intent')!='adopt-definite-suggestions' or set(auth.get('ids',[]))!=set(changes):
                    raise ValueError('Bulk adoption requires explicit exact-ID authorization')
                for i,v in changes.items():
                    if base['items'][i]['decision']!='pending' or self.by[i]['suggestion'] not in {'keep','delete'}:
                        raise ValueError('Bulk adoption must preserve manual decisions and uncertainty')
                    if v.get('decision')!=self.by[i]['suggestion']:raise ValueError('Bulk action differs from suggestion')
            elif operation=='import':
                auth=body.get('authorization',{})
                if not isinstance(auth,dict):raise ValueError('Invalid authorization')
                if auth.get('intent')!='restore-backup' or set(auth.get('ids',[]))!=set(changes):
                    raise ValueError('Restoring a backup requires exact-ID authorization')
            elif operation!='item' or len(changes)!=1:raise ValueError('Invalid operation')
            result,conflicts=merge_items(base['items'],old['items'],changes)
            if conflicts:return None,conflicts
            # Atomic snapshots precede replacement; old browser backups also remain exportable.
            snapshot=self.root/'backups'/f'r{old["revision"]:06}.json'
            if not snapshot.exists():atomic(snapshot,old)
            new={'binding':self.binding,'revision':old['revision']+1,'items':result,'updated_at':now()}
            with (self.root/'history.jsonl').open('ab') as f:
                f.write(canonical({'at':now(),'base_revision':revision,'revision':new['revision'],
                                   'operation':operation,'card_id':body.get('card_id'),
                                   'authorization':body.get('authorization'),'changes':changes})+b'\n');f.flush();os.fsync(f.fileno())
            atomic(self.root/'state.json',new)
            return new,{}


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def json(self,status,value):
            data=canonical(value);self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def allowed(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def do_GET(self):
            if not self.allowed():return self.send_error(403)
            route=self.path.split('?')[0]
            if route=='/health':return self.json(200,{'binding':store.binding,'service':'paragraph-review-v1','project':hashlib.sha256(str(store.root).encode()).hexdigest()})
            if route=='/data':return self.json(200,store.data)
            if route=='/progress':
                with store.lock:return self.json(200,store.read())
            if route=='/':path=Path(__file__).resolve().parents[1]/'assets/paragraph-review.html'
            elif route=='/audio':path=Path(store.manifest['audio'])
            else:return self.send_error(404)
            size=path.stat().st_size;start,end,status=0,size-1,200
            if self.headers.get('Range'):
                m=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers['Range'])
                if not m or not any(m.groups()):return self.send_error(416)
                if m[1]:start=int(m[1]);end=min(end,int(m[2]) if m[2] else end)
                else:start=max(0,size-int(m[2]))
                if start>end or start>=size:return self.send_error(416)
                status=206
            self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
            self.send_header('Cache-Control','no-cache');self.send_header('X-Content-Type-Options','nosniff')
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            try:
                with path.open('rb') as f:
                    f.seek(start);left=end-start+1
                    while left:
                        data=f.read(min(262144,left))
                        if not data:break
                        self.wfile.write(data);left-=len(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_POST(self):
            if not self.allowed() or self.headers.get('Origin')!=f'http://127.0.0.1:{self.server.server_port}':return self.send_error(403)
            if self.path!='/progress':return self.send_error(404)
            try:
                n=int(self.headers.get('Content-Length',0))
                if not 0<n<=4000000:raise ValueError('Invalid request size')
                body=json.loads(self.rfile.read(n))
                if not isinstance(body,dict):raise ValueError('Invalid request object')
                state,conflicts=store.apply(body)
                if conflicts:return self.json(409,{'conflicts':conflicts,'message':'Same-field decisions conflict; export and explicitly choose a value'})
                self.json(200,state)
            except (ValueError,TypeError,KeyError,FileNotFoundError) as e:self.json(400,{'error':str(e)})
    return Handler


def launch(root,port):
    root=Path(root).resolve();binding=Store(root).binding;project=hashlib.sha256(str(root).encode()).hexdigest()
    for candidate in range(port,port+10):
        url=f'http://127.0.0.1:{candidate}'
        try:
            value=json.load(urllib.request.urlopen(url+'/health',timeout=.5))
            if value.get('service')=='paragraph-review-v1' and value.get('binding')==binding and value.get('project')==project:return url
            continue
        except Exception:pass
        with (root/'server.log').open('ab') as log:
            proc=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'serve',str(root),'--port',str(candidate)],
                                  stdout=log,stderr=log,start_new_session=True)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if proc.poll() is not None:break
            try:
                value=json.load(urllib.request.urlopen(url+'/health',timeout=.3))
                if value.get('binding')==binding and value.get('project')==project:return url
            except Exception:time.sleep(.1)
        if proc.poll() is None:raise RuntimeError('Review service is still validating media; do not launch another process, inspect server.log')
    raise RuntimeError('No matching review service started; inspect server.log')


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('spec',type=Path);b.add_argument('output',type=Path)
    for name in ('serve','launch'):
        p=sub.add_parser(name);p.add_argument('root',type=Path);p.add_argument('--port',type=int,default=8877)
    args=parser.parse_args()
    if args.command=='build':build(args.spec,args.output)
    elif args.command=='launch':print(launch(args.root,args.port))
    else:
        store=Store(args.root);server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(store))
        print(f'http://127.0.0.1:{server.server_port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()


if __name__=='__main__':main()
