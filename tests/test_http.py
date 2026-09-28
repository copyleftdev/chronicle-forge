import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from chronicle_forge.generate import generate
from chronicle_forge.simulator import make_server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='forge-http-')
        root=generate(Path(cls.tmp.name)/'corpus')
        cls.server=make_server(root,port=0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()

    def request(self,path,body=None,headers=None):
        request=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body else None,headers=headers or {})
        try:
            with urllib.request.urlopen(request,timeout=3) as r:return r.status,dict(r.headers),json.load(r)
        except urllib.error.HTTPError as e:
            try:
                raw=e.read();return e.code,dict(e.headers),json.loads(raw) if raw else None
            finally:e.close()

    def test_etag_and_pagination(self):
        path='/objects?kind=comment&first=3&at=2020-02-01T00:08:00Z'
        status,headers,data=self.request(path)
        self.assertEqual(status,200);self.assertEqual(len(data['nodes']),3)
        self.assertTrue(data['pageInfo']['hasNextPage'])
        self.assertEqual(self.request(path,headers={'If-None-Match':headers['ETag']})[0],304)

    def test_fault_and_expiry(self):
        status,headers,_=self.request('/objects?fault=rate_limit')
        self.assertEqual(status,429);self.assertEqual(headers['Retry-After'],'1')
        self.assertEqual(self.request('/objects?fault=unavailable')[0],503)
        self.assertEqual(self.request('/objects/LOG1?at=2020-02-06T00:00:00Z')[0],410)

    def test_graphql_shaped_errors(self):
        status,_,data=self.request('/graphql',{'operationName':'Object','variables':{'id':'PRIVATE1','at':'2020-06-01T00:00:00Z'}})
        self.assertEqual(status,200);self.assertEqual(data['errors'][0]['status'],404)
        self.assertEqual(self.request('/graphql',{'operationName':'Object','variables':{'id':'PR1'}})[2]['data']['id'],'PR1')

    def test_no_oracle_endpoint(self):
        for path in ['/oracle/manifest.json','/simulator/events.json','/../oracle/manifest.json']:
            self.assertEqual(self.request(path)[0],404)

    def test_bad_requests(self):
        self.assertEqual(self.request('/objects?first=-1')[0],400)
        self.assertEqual(self.request('/objects?at=tomorrow')[0],400)
        self.assertIn('errors',self.request('/graphql',{'query':'{ viewer { login } }'})[2])


if __name__=='__main__':unittest.main()
