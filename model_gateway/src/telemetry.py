"""LiteLLM events contain identifiers and timings, never prompts or credentials."""

from litellm.integrations.custom_logger import CustomLogger
from shared_libs.logging import emit


class ModelLogger(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        emit(
            "model.completed",
            logical_model=kwargs.get("model"),
            status_code=200,
            duration_ms=max(0, (end_time - start_time).total_seconds() * 1000),
        )

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        emit(
            "model.failed",
            logical_model=kwargs.get("model"),
            error_code=type(kwargs.get("exception")).__name__,
            duration_ms=max(0, (end_time - start_time).total_seconds() * 1000),
        )


model_logger = ModelLogger(turn_off_message_logging=True)
