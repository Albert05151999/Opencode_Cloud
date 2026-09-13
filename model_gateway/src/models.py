"""Compile explicitly supplied draft models without publishing them."""

from fastapi import HTTPException


def compile_model(model):
    providers = {
        "openai-compatible": "openai",
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "gemini",
    }
    if (
        model.get("provider") not in providers
        or not model.get("upstream_model")
        or not model.get("id")
    ):
        raise HTTPException(400, "Unsupported provider or missing model identity")
    if not model.get("api_key") or model.get("api_key") == "••••":
        raise HTTPException(400, "Enter a model API key before testing")
    params = {
        "model": providers[model["provider"]] + "/" + model["upstream_model"],
        "api_key": model["api_key"],
        **model.get("parameters", {}),
    }
    if model.get("base_url"):
        params["api_base"] = model["base_url"]
    if model.get("headers"):
        params["extra_headers"] = model["headers"]
    entries = [
        {
            "model_name": model["id"],
            "litellm_params": params,
            "model_info": {"id": model["id"]},
        }
    ]
    for index, base in enumerate(model.get("additional_base_urls", [])):
        entries.append(
            {
                "model_name": model["id"],
                "litellm_params": {**params, "api_base": base},
                "model_info": {"id": model["id"] + "-extra-" + str(index)},
            }
        )
    return {"model_list": entries, "router_settings": {"num_retries": 0, "timeout": 60}}
