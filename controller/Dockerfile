FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/controller

COPY requirements-controller.lock /tmp/requirements-controller.lock
RUN test "$(python --version)" = "Python 3.12.3" \
    && python -m pip install --no-cache-dir --require-hashes --only-binary=:all: \
        --requirement /tmp/requirements-controller.lock \
    && python -m pip check \
    && rm -f /tmp/requirements-controller.lock \
    && mkdir -p /srv/cloud-agent/workspaces /srv/cloud-agent/state \
    && chown -R 10001:10001 /srv/cloud-agent/workspaces /srv/cloud-agent/state

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY docs/upstream/opencode-1.18.29-openapi.json ./docs/upstream/opencode-1.18.29-openapi.json

# Run as root for Docker socket access. Deployment must use host networking and
# mount /var/run/docker.sock, /srv/cloud-agent/config.cfg, agents, and data roots.
ENTRYPOINT ["python", "-m", "app.main", "--config", "/srv/cloud-agent/config.cfg"]
