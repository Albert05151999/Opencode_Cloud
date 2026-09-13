ARG CONTROLLER_BASE_IMAGE
FROM ${CONTROLLER_BASE_IMAGE}
ARG PYTHON_VERSION
RUN test "$(python --version)" = "Python ${PYTHON_VERSION}"
WORKDIR /opt/cloud
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MODULE_CONFIG=/config/config.json
COPY model_gateway/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --requirement /tmp/requirements.lock && pip check
COPY model_gateway/ /opt/cloud/model_gateway/
COPY shared_libs/ /opt/cloud/shared_libs/
COPY config.json /config/config.json
CMD ["python", "-m", "model_gateway.main"]
