"""Typed public operations API; runtime actions live in the service."""
import asyncio
from fastapi import APIRouter, Query
from pydantic import Field

from app.admin_dto import DTO
from app.recovery import RecoveryPolicy


class OperationRequest(DTO):
    request_id: str = Field(min_length=8, max_length=128)
    revision: int | None = None


class DeleteRequest(OperationRequest):
    preview_id: str
    confirmation: str


class SandboxRequest(OperationRequest):
    force_preview_id: str | None = None
    confirmation: str | None = None


def create_operations_router(runtime):
    router = APIRouter(tags=['platform-operations'])
    operations = runtime.operations
    from app.job_coordinator import JobCoordinator
    coordinator = JobCoordinator(operations.store)

    @router.get('/cloud/admin/jobs')
    def jobs(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), target: str | None = None):
        return coordinator.list(offset, limit, target)

    @router.post('/cloud/admin/jobs/{jid}/cancel')
    def cancel_job(jid: str):
        return coordinator.cancel(jid)

    @router.get('/cloud/admin/sandboxes/{sid}')
    async def sandbox_detail(sid: str):
        return await operations.details.detail(sid)

    @router.get('/cloud/admin/sandboxes/{sid}/force-preview')
    async def force_preview(sid: str):
        return await operations.details.preview(sid)

    @router.get('/cloud/admin/sandboxes')
    def sandboxes(q: str = '', status: str | None = None,
                  offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        return operations.list(q, status, offset, limit)

    @router.get('/cloud/admin/recovery-policy')
    def policy():
        return operations.recovery.policy()

    @router.put('/cloud/admin/recovery-policy')
    def save_policy(payload: RecoveryPolicy):
        operations.recovery.save_policy(payload)
        return operations.recovery.policy()

    @router.get('/cloud/admin/agents/{aid}/delete-preview')
    def delete_preview(aid: str):
        return operations.deletion.preview(aid)

    @router.post('/cloud/admin/agents/{aid}/delete')
    async def delete_agent(aid: str, payload: DeleteRequest):
        from app.management import fail
        for job in operations.store.read()[1]['jobs'].values():
            if job.get('request_id') == payload.request_id:
                if job['kind'] != 'agent.delete' or job['payload']['resource_id'] != aid:
                    fail('Request ID was already used for another operation', 409)
                return {'job_id': job['id']}
        impact = await asyncio.to_thread(operations.deletion.authorize, aid, payload.preview_id, payload.confirmation)
        jid, created = operations.submit('agent.delete', aid, payload.request_id, impact['revision'], impact['fingerprint'])
        if created:
            runtime.spawn(operations.run(jid))
        return {'job_id': jid}

    async def submit(kind, target, payload):
        from app.management import fail
        for job in operations.store.read()[1]['jobs'].values():
            if job.get('request_id') == payload.request_id:
                if job['kind'] != kind or job['payload']['resource_id'] != target:
                    fail('Request ID was already used for another operation',409)
                return {'job_id':job['id']}
        force = None
        if getattr(payload, 'force_preview_id', None):
            force = operations.details.authorize(target, payload.force_preview_id, payload.confirmation)
        jid, created = operations.submit(kind, target, payload.request_id, payload.revision, force=force)
        if created:
            runtime.spawn(operations.run(jid))
        return {'job_id': jid}

    @router.post('/cloud/admin/sandboxes/{sid}/start')
    async def start(sid: str, payload: OperationRequest):
        return await submit('sandbox.start', sid, payload)

    @router.post('/cloud/admin/sandboxes/{sid}/stop')
    async def stop(sid: str, payload: SandboxRequest):
        return await submit('sandbox.stop', sid, payload)

    @router.post('/cloud/admin/sandboxes/{sid}/restart')
    async def restart(sid: str, payload: SandboxRequest):
        return await submit('sandbox.restart', sid, payload)

    @router.post('/cloud/admin/agents/{aid}/archive')
    async def archive(aid: str, payload: OperationRequest):
        return await submit('agent.archive', aid, payload)

    @router.post('/cloud/admin/agents/{aid}/restore')
    async def restore(aid: str, payload: OperationRequest):
        return await submit('agent.restore', aid, payload)

    @router.post('/cloud/admin/agents/{aid}/delete-empty')
    async def delete_empty(aid: str, payload: OperationRequest):
        return await submit('agent.delete-empty', aid, payload)

    return router
