import json
from typing import Literal

from fastapi import APIRouter, Query
from starlette.responses import Response

from app.admin_dto import DTO
from app.load_test_store import LoadRequest, report_csv


class CleanupRequest(DTO):
    confirmation: str


def create_load_test_router(service):
    router = APIRouter(prefix='/cloud/admin/load-tests', tags=['load-testing'])

    @router.get('/options')
    async def options():
        return await service.options()

    @router.get('/capacity')
    async def capacity():
        return await service.capacity.snapshot()

    @router.get('')
    def listing(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
        return service.store.list(offset, limit)

    @router.post('', status_code=202)
    async def start(payload: LoadRequest):
        return await service.admit_start(payload)

    @router.get('/{rid}')
    def detail(rid: str):
        return service.store.get(rid)

    @router.post('/{rid}/cancel', status_code=202)
    async def cancel(rid: str):
        return service.cancel(rid)

    @router.post('/{rid}/cleanup', status_code=202)
    async def cleanup(rid: str, payload: CleanupRequest):
        return service.cleanup(rid, payload.confirmation)

    @router.get('/{rid}/report')
    def report(rid: str, format: Literal['json', 'csv'] = 'json'):
        result = service.store.get(rid)
        content = report_csv(result) if format == 'csv' else json.dumps(result, ensure_ascii=False, indent=2)
        return Response(content, media_type='text/csv; charset=utf-8' if format == 'csv' else 'application/json',
                        headers={'Content-Disposition': f'attachment; filename="{result["id"]}.{format}"'})

    return router
