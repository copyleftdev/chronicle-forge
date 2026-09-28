"""A documented API subset, not a full GitHub emulator. Oracle never loaded."""
import base64
import hashlib
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class APIError(Exception):
    def __init__(self,status,message):
        self.status=status
        super().__init__(message)


def instant(value):
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('timezone required')
        return parsed.astimezone(timezone.utc)
    except (ValueError,AttributeError,TypeError):
        raise APIError(400,'Expected ISO-8601 timestamp with timezone')


class Simulator:
    def __init__(self,corpus):
        self.events=json.loads((Path(corpus)/'simulator/events.json').read_text())
        self.digest=hashlib.sha256(json.dumps(self.events,sort_keys=True).encode()).hexdigest()

    def snapshot(self,at,role='public'):
        clock=instant(at)
        if role not in ('public','member'):raise APIError(400,'role must be public or member')
        state={}
        for event in self.events:
            if instant(event['at'])>clock:continue
            identifier=event['entity']
            if event['action']=='delete':state.pop(identifier,None)
            else:
                obj=state.setdefault(identifier,{'id':identifier,'created_at':event['at']})
                obj.update(event['data']);obj['updated_at']=event['at']
        return {k:v for k,v in state.items() if role=='member' or v.get('visibility','public')=='public'}

    def get(self,identifier,at,role='public'):
        obj=self.snapshot(at,role).get(identifier)
        if obj is None:raise APIError(404,'Not found or not visible')
        if obj.get('expires_at') and instant(at)>=instant(obj['expires_at']):
            raise APIError(410,'Evidence expired')
        return obj

    def page(self,at,kind=None,pr=None,first=3,after=None,role='public'):
        if type(first) is not int or not 1<=first<=100:raise APIError(400,'first must be 1..100')
        state=self.snapshot(at,role)
        rows=sorted((obj for obj in state.values() if (kind is None or obj['kind']==kind)
                     and (pr is None or obj.get('pr')==pr)
                     and not (obj.get('expires_at') and instant(at)>=instant(obj['expires_at']))),key=lambda x:x['id'])
        signature=hashlib.sha256(json.dumps([self.digest,at,kind,pr,role],sort_keys=True).encode()).hexdigest()
        offset=0
        if after:
            try:
                value=json.loads(base64.urlsafe_b64decode(after.encode()))
                if value['snapshot']!=signature:raise APIError(409,'Cursor belongs to a different view')
                offset=value['offset']
                if type(offset) is not int or offset<0 or offset>len(rows):raise ValueError()
            except APIError:raise
            except (ValueError,KeyError,TypeError,UnicodeError):raise APIError(400,'Invalid cursor')
        nodes=rows[offset:offset+first];end=offset+len(nodes)
        cursor=base64.urlsafe_b64encode(json.dumps({'snapshot':signature,'offset':end}).encode()).decode() if nodes else None
        return {'nodes':nodes,'totalCount':len(rows),'pageInfo':{'hasNextPage':end<len(rows),'endCursor':cursor},
                'observed_at':at,'synthetic':True}


def make_server(corpus,host='127.0.0.1',port=8765):
    simulator=Simulator(corpus)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass

        def respond(self,status,data,headers=None):
            body=json.dumps(data,sort_keys=True).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('X-Chronicle-Forge','synthetic')
            for key,value in (headers or {}).items():self.send_header(key,value)
            self.end_headers();self.wfile.write(body)

        def do_GET(self):
            parsed=urlparse(self.path);q={k:v[-1] for k,v in parse_qs(parsed.query).items()}
            try:
                if q.get('fault')=='rate_limit':
                    self.respond(429,{'error':'Synthetic rate limit'},{'Retry-After':'1'});return
                if q.get('fault')=='unavailable':raise APIError(503,'Synthetic outage')
                at=q.get('at','2020-02-01T00:08:00Z');role=q.get('role','public')
                if parsed.path=='/health':data={'synthetic':True,'status':'ok'}
                elif parsed.path=='/objects':
                    try:first=int(q.get('first','3'))
                    except ValueError:raise APIError(400,'first must be an integer')
                    data=simulator.page(at,q.get('kind'),q.get('pr'),first,q.get('after'),role)
                elif parsed.path.startswith('/objects/'):
                    data=simulator.get(parsed.path.removeprefix('/objects/'),at,role)
                else:raise APIError(404,'Unknown endpoint')
                etag='"'+hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()+'"'
                if self.headers.get('If-None-Match')==etag:
                    self.send_response(304);self.send_header('ETag',etag);self.end_headers();return
                self.respond(200,data,{'ETag':etag})
            except APIError as error:self.respond(error.status,{'error':str(error),'synthetic':True})

        def do_POST(self):
            # Fixed operation interface. Arbitrary GraphQL text is intentionally unsupported.
            try:
                if self.path!='/graphql':raise APIError(404,'Unknown endpoint')
                size=int(self.headers.get('Content-Length','0'))
                if size<1 or size>65536:raise APIError(413,'Body must be 1..65536 bytes')
                body=json.loads(self.rfile.read(size));variables=body.get('variables',{})
                if 'query' in body:raise APIError(400,'Query text unsupported; use named operationName and variables')
                operation=body.get('operationName');at=variables.get('at','2020-02-01T00:08:00Z')
                if operation=='Object':data=simulator.get(variables['id'],at,variables.get('role','public'))
                elif operation=='Objects':data=simulator.page(at,variables.get('kind'),variables.get('pr'),
                    variables.get('first',3),variables.get('after'),variables.get('role','public'))
                else:raise APIError(400,'Supported operations: Object, Objects')
                self.respond(200,{'data':data,'synthetic':True})
            except APIError as error:
                self.respond(200,{'errors':[{'message':str(error),'status':error.status}],'synthetic':True})
            except (ValueError,KeyError,TypeError,AttributeError):
                self.respond(400,{'error':'Invalid request'})
    return ThreadingHTTPServer((host,port),Handler)


def serve(corpus,host='127.0.0.1',port=8765):
    server=make_server(corpus,host,port)
    print(f'Chronicle Forge simulator: http://{host}:{server.server_port}',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
