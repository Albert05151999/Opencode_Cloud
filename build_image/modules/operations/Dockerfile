ARG CONTROLLER_BASE_IMAGE
FROM ${CONTROLLER_BASE_IMAGE}
ARG PYTHON_VERSION
RUN test "$(python --version)" = "Python ${PYTHON_VERSION}"
WORKDIR /opt/cloud
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MODULE_CONFIG=/config/config.json
COPY operations/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --requirement /tmp/requirements.lock && pip check
COPY operations/ /opt/cloud/operations/
COPY shared_libs/ /opt/cloud/shared_libs/
COPY config.json /config/config.json
CMD ["python", "-m", "operations.main"]
