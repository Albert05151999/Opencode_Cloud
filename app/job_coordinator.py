"""Persisted job query/cancellation rules shared by all runtime services."""
import time

from app.management import fail, redact


class JobCancelled(Exception):
    pass


class JobCoordinator:
    def __init__(self, store):
        self.store = store

    def list(self, offset=0, limit=25, target=None):
        jobs = [j for j in self.store.read()[1]['jobs'].values() if not target or j['target']==target]
        jobs.sort(key=lambda j:j['created'], reverse=True)
        fields = ('id','kind','target','status','created','updated','error','checkpoint','result','interrupted_sessions','recovered')
        return {'total':len(jobs),'items':[redact({k:j[k] for k in fields if k in j}) for j in jobs[offset:offset+limit]]}

    def cancel(self, jid):
        with self.store.edit() as data:
            job = data['jobs'].get(jid)
            if not job:
                fail('Job not found',404)
            if job['status']=='cancelled':
                return {'id':jid,'status':'cancelled'}
            if job['status'] not in {'queued','validating','waiting'}:
                fail('Job has reached the apply phase and cannot be cancelled',409)
            if job['kind']=='agent.delete':
                fail('Permanent deletion cannot be cancelled; inspect deletion status',409)
            job.update(status='cancelled', updated=time.time())
        return {'id':jid,'status':'cancelled'}
