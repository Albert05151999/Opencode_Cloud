# syntax=docker/dockerfile:1
FROM python:3.12.3-slim@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63 AS certificates
FROM ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517

ARG NODE_VERSION=24.20.0
ARG OPENCODE_VERSION=1.18.29
ARG NODE_ARCHIVE_SHA256=2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2
ARG UBUNTU_SNAPSHOT=20260907T000000Z
ARG TARGETARCH

LABEL org.opencontainers.image.title="OpenCode Cloud Agent Runtime" \
      cloud.node.version="${NODE_VERSION}" \
      cloud.opencode.version="${OPENCODE_VERSION}"

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    NODE_VERSION=${NODE_VERSION} \
    OPENCODE_VERSION=${OPENCODE_VERSION} \
    OPENCODE_DISABLE_AUTOUPDATE=1 \
    OPENCODE_DISABLE_MODELS_FETCH=1 \
    OPENCODE_DISABLE_DEFAULT_PLUGINS=1 \
    OPENCODE_DISABLE_LSP_DOWNLOAD=1 \
    OPENCODE_CONFIG=/opt/agent/opencode.json \
    XDG_DATA_HOME=/state/opencode/data \
    XDG_CACHE_HOME=/tmp/opencode-cache \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN printf 'Types: deb\nURIs: https://snapshot.ubuntu.com/ubuntu/%s\nSuites: noble noble-updates noble-security\nComponents: main universe\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\nSnapshot: no\n' "$UBUNTU_SNAPSHOT" > /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o APT::Update::Error-Mode=any update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        xz-utils \
    && test "$(python3 --version)" = "Python 3.12.3" \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    test "${TARGETARCH:-amd64}" = amd64; \
    archive="node-v${NODE_VERSION}-linux-x64.tar.xz"; \
    base_url="https://nodejs.org/dist/v${NODE_VERSION}"; \
    curl --fail --location --retry 3 --max-time 180 "${base_url}/${archive}" --output "/tmp/${archive}"; \
    curl --fail --location --retry 3 --max-time 30 "${base_url}/SHASUMS256.txt" --output /tmp/SHASUMS256.txt; \
    cd /tmp; \
    grep "  ${archive}$" SHASUMS256.txt | sha256sum --check -; \
    printf '%s  %s\n' "$NODE_ARCHIVE_SHA256" "$archive" | sha256sum --check -; \
    tar -xJf "${archive}" -C /opt; \
    for executable in node npm npx; do \
        ln -s "/opt/node-v${NODE_VERSION}-linux-x64/bin/${executable}" "/usr/local/bin/${executable}"; \
    done; \
    rm -f "/tmp/${archive}" /tmp/SHASUMS256.txt; \
    test "$(node --version)" = "v${NODE_VERSION}"

COPY runtime/package.json runtime/package-lock.json /opt/opencode/
RUN cd /opt/opencode \
    && npm ci --ignore-scripts --no-audit --no-fund \
    && cd node_modules/opencode-ai && node postinstall.mjs \
    && ln -s /opt/opencode/node_modules/.bin/opencode /usr/local/bin/opencode \
    && test "$(opencode --version)" = "${OPENCODE_VERSION}" \
    && npm cache clean --force

COPY runtime/requirements.lock /tmp/runtime-requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes --only-binary=:all: --requirement /tmp/runtime-requirements.txt \
    && /opt/venv/bin/pip check \
    && rm -f /tmp/runtime-requirements.txt

RUN groupadd --gid 10001 agent \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/agent --shell /bin/bash agent \
    && install --directory --owner=agent --group=agent /workspace /state/opencode /tmp/opencode-cache \
    && install --directory --owner=root --group=root --mode=0755 /opt/agent/global/opencode \
    && touch /opt/agent/global/opencode/.gitignore

COPY --chown=root:root runtime/opencode/global/opencode.json /opt/agent/opencode.json
COPY --chown=root:root runtime/entrypoint.sh /usr/local/bin/runtime-entrypoint
COPY --chown=root:root runtime/smoke/image-smoke.sh /opt/runtime/image-smoke.sh
RUN chmod 0755 /usr/local/bin/runtime-entrypoint /opt/runtime/image-smoke.sh \
    && chmod 0644 /opt/agent/opencode.json

RUN rg --version

USER agent:agent
WORKDIR /workspace
EXPOSE 4096

ENTRYPOINT ["/usr/local/bin/runtime-entrypoint"]
