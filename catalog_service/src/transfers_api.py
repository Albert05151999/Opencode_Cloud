import asyncio
from fastapi import APIRouter, File, UploadFile, Form
from pydantic import Field
from starlette.responses import Response

from catalog_service.src.admin_dto import DTO, ResourceID, VersionBinding
from catalog_service.src.transfers import Transfers, LIMIT


class Selection(DTO):
    key: str
    target_id: ResourceID
    replace: bool = False


class ImportCommit(DTO):
    selections: list[Selection] = Field(min_length=1, max_length=1000)


class EncryptedExport(DTO):
    password: str = Field(min_length=12, max_length=1024)
    include_credentials: bool = False


class TemplateRestore(DTO):
    agent_id: ResourceID
    models: dict[str, ResourceID] = Field(default_factory=dict)
    resources: dict[str, VersionBinding] = Field(default_factory=dict)


def create_transfers_router(store, runtime=None):
    router = APIRouter(tags=["resource-transfer"])
    service = Transfers(store, runtime)
    from catalog_service.src.agent_templates import AgentTemplates

    templates = AgentTemplates(store)

    @router.get("/cloud/admin/exports/native/{aid}")
    def native_export(aid: str):
        from catalog_service.src.native_export import export_native

        return Response(
            export_native(runtime, aid),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="opencode-native.zip"'
            },
        )

    @router.get("/cloud/admin/agent-templates")
    def template_list():
        return templates.list()

    @router.post("/cloud/admin/agent-templates/{tid}/restore")
    def restore_template(tid: str, payload: TemplateRestore):
        return templates.restore(
            tid,
            payload.agent_id,
            payload.models,
            {key: value.model_dump() for key, value in payload.resources.items()},
        )

    @router.post("/cloud/admin/imports/preview")
    async def preview(file: UploadFile = File(), password: str | None = Form(None)):
        content = await file.read((LIMIT * 2 if password else LIMIT) + 1)
        return await asyncio.to_thread(
            service.preview, file.filename or "config.json", content, password
        )

    @router.post("/cloud/admin/exports/encrypted")
    def encrypted(payload: EncryptedExport):
        from catalog_service.src.encrypted_transfer import encrypt

        content = encrypt(service.export(payload.include_credentials), payload.password)
        return Response(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="cloud-resources.encrypted.json"'
            },
        )

    @router.post("/cloud/admin/imports/{preview_id}/commit")
    def commit(preview_id: str, payload: ImportCommit):
        return service.commit(preview_id, [s.model_dump() for s in payload.selections])

    @router.get("/cloud/admin/exports/resources")
    def export():
        return Response(
            service.export(),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="cloud-resources.json"'
            },
        )

    return router
