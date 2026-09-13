ARG CONTROLLER_BASE_IMAGE
FROM ${CONTROLLER_BASE_IMAGE}
ARG PYTHON_VERSION
RUN test "$(python --version)" = "Python ${PYTHON_VERSION}"
WORKDIR /opt/cloud
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MODULE_CONFIG=/config/config.json
COPY api_gateway/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --requirement /tmp/requirements.lock && pip check
COPY api_gateway/ /opt/cloud/api_gateway/
COPY shared_libs/ /opt/cloud/shared_libs/
COPY config.json /config/config.json
CMD ["python", "-m", "api_gateway.main"]
