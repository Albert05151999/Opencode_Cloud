"""Compile explicitly supplied draft models without publishing them."""

from fastapi import HTTPException
from shared_libs.model_routing import deployment_entries, ROUTER_SETTINGS


def compile_model(model):
    try:
        return {'model_list': deployment_entries(model, require_credentials=True),
                'router_settings': {**ROUTER_SETTINGS, 'num_retries': 0, 'timeout': 60}}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
