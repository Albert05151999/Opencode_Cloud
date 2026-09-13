from fastapi import FastAPI
from starlette.responses import Response
from api_gateway.api_docs import create_docs_router
from shared_libs.metrics import PlatformMetrics, MetricsMiddleware

def create_router_app(gateway_router=None, *,cloud_routers=(),metrics=None,**kwargs):
    app=FastAPI()
    if metrics:
        app.add_middleware(MetricsMiddleware,metrics=metrics)
        app.add_api_route("/metrics",lambda: Response(metrics.render(),media_type="text/plain"))
    for router in cloud_routers:app.include_router(router)
    app.add_api_route("/cloud/health",lambda: {"ok":True})
    app.include_router(create_docs_router())
    if gateway_router:app.include_router(gateway_router)
    return app
