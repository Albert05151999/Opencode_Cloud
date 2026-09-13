ARG CONTROLLER_BASE_IMAGE
FROM ${CONTROLLER_BASE_IMAGE}
ARG PYTHON_VERSION
RUN test "$(python --version)" = "Python ${PYTHON_VERSION}"
WORKDIR /opt/cloud
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MODULE_CONFIG=/config/config.json
COPY catalog_service/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --requirement /tmp/requirements.lock && pip check
COPY catalog_service/ /opt/cloud/catalog_service/
COPY shared_libs/ /opt/cloud/shared_libs/
COPY config.json /config/config.json
CMD ["python", "-m", "catalog_service.main"]
