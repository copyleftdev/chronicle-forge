import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from chronicle_forge.generate import generate
from chronicle_forge.simulator import Simulator, APIError


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='chronicle-tests-')
        cls.root=generate(Path(cls.tmp.name)/'a',42)
        cls.other=generate(Path(cls.tmp.name)/'b',42)
        cls.sim=Simulator(cls.root)
        cls.manifest=json.loads((cls.root/'oracle/manifest.json').read_text())
        cls.oid=cls.manifest['objects']

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root/'evidence/repo'),*args],text=True).strip()

    def test_reproducible_objects_and_events(self):
        self.assertEqual(self.manifest,json.loads((self.other/'oracle/manifest.json').read_text()))
        self.assertEqual((self.root/'simulator/events.json').read_bytes(),(self.other/'simulator/events.json').read_bytes())

    def test_refuse_overwrite(self):
        with self.assertRaises(ValueError):generate(self.root)

    def test_merge_and_squash(self):
        self.assertEqual(len(self.git('show','-s','--format=%P',self.oid['merge']).split()),2)
        self.assertEqual(len(self.git('show','-s','--format=%P',self.oid['squash']).split()),1)
        self.assertNotEqual(self.oid['after_amend'],self.oid['squash'])
        self.assertEqual(self.git('rev-parse',self.oid['after_amend']+'^{tree}'),self.git('rev-parse',self.oid['squash']+'^{tree}'))

    def test_backport_and_extra(self):
        self.assertIn(self.oid['feature'],self.git('show','-s','--format=%B',self.oid['backport']))
        self.assertIn('compatibility.txt',self.git('diff','--name-only',self.oid['backport'],self.oid['backport_extra']))

    def test_rename_revert(self):
        self.assertIn('R100',self.git('diff-tree','--no-commit-id','--name-status','-r','-M',self.oid['rename']))
        self.assertEqual(self.git('show',self.oid['revert']+':dependencies.lock'),'codec=1.0')

    def test_local_evidence(self):
        info=json.loads((self.root/'evidence/local/inspection.json').read_text())
        self.assertIn('unreachable commit '+self.oid['before_amend'],info['unreachable_ignoring_reflogs'])
        self.assertTrue(any(x.endswith('/postimage') for x in info['rerere_files']))
        self.assertIn('Unfinished experiment',info['stash'])
        conflict=json.loads((self.root/'evidence/local/conflict.json').read_text())
        for stage in (1,2,3):self.assertIn(f' {stage}\tsettings.txt',conflict['index_stages'])

    def test_pagination_complete_no_duplicates(self):
        cursor=None;ids=[]
        while True:
            page=self.sim.page('2020-02-01T00:08:00Z',kind='comment',first=3,after=cursor)
            ids.extend(x['id'] for x in page['nodes'])
            if not page['pageInfo']['hasNextPage']:break
            cursor=page['pageInfo']['endCursor']
        self.assertEqual(len(ids),8);self.assertEqual(len(set(ids)),8)

    def test_stale_cursor(self):
        cursor=self.sim.page('2020-02-01T00:08:00Z',kind='comment')['pageInfo']['endCursor']
        with self.assertRaises(APIError) as caught:self.sim.page('2020-02-02T00:00:00Z',kind='comment',after=cursor)
        self.assertEqual(caught.exception.status,409)

    def test_edit_delete_and_identity(self):
        self.assertNotEqual(self.sim.get('C8','2020-02-01T00:08:00Z')['body'],self.sim.get('C8','2020-02-01T00:10:00Z')['body'])
        with self.assertRaises(APIError):self.sim.get('C2','2020-02-02T00:00:00Z')
        self.assertEqual(self.sim.get('U1','2020-06-01T00:00:00Z')['login'],'forge-mira-renamed')

    def test_retention_and_access(self):
        self.assertIn('FAILED',self.sim.get('LOG1','2020-02-02T00:00:00Z')['body'])
        with self.assertRaises(APIError) as caught:self.sim.get('LOG1','2020-02-06T00:00:00Z')
        self.assertEqual(caught.exception.status,410)
        with self.assertRaises(APIError):self.sim.get('PRIVATE1','2020-06-01T00:00:00Z')
        self.assertEqual(self.sim.get('PRIVATE1','2020-06-01T00:00:00Z','member')['id'],'PRIVATE1')

    def test_future_and_timezone(self):
        self.assertNotIn('PR5',self.sim.snapshot('2039-12-31T23:59:59Z'))
        self.assertIn('PR5',self.sim.snapshot('2040-01-01T01:00:00+01:00'))
        self.assertIn('2040',self.git('show','-s','--format=%aI',self.oid['future']))

    def test_simulator_never_needs_oracle(self):
        # Build an evidence service with only the private backing store.
        isolated=Path(self.tmp.name)/'service';(isolated/'simulator').mkdir(parents=True,exist_ok=True)
        (isolated/'simulator/events.json').write_bytes((self.root/'simulator/events.json').read_bytes())
        self.assertEqual(Simulator(isolated).get('PR1','2020-02-02T00:00:00Z')['state'],'MERGED')

    def test_run_attempts_not_names(self):
        a=self.sim.get('RUN1','2020-02-02T00:00:00Z');b=self.sim.get('RUN1A2','2020-02-02T00:00:00Z');c=self.sim.get('RUN2','2020-02-02T00:00:00Z')
        self.assertEqual(a['run_id'],b['run_id']);self.assertNotEqual(a['attempt'],b['attempt'])
        self.assertEqual(a['name'],c['name']);self.assertNotEqual(a['run_id'],c['run_id'])

    def test_rebase_and_clone_boundary(self):
        self.assertNotEqual(self.oid['before_rebase'],self.oid['after_rebase'])
        self.assertEqual(self.git('show','-s','--format=%P',self.oid['after_rebase']),self.oid['rebase_base'])
        clone=self.root/'evidence/transport-clone'
        self.assertFalse((clone/'.git/rr-cache').exists())
        self.assertEqual(subprocess.check_output(['git','-C',str(clone),'stash','list'],text=True),'')
        r=subprocess.run(['git','-C',str(clone),'cat-file','-e',self.oid['before_amend']],capture_output=True)
        self.assertNotEqual(r.returncode,0)


if __name__=='__main__':unittest.main()
