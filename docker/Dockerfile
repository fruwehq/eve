# syntax=docker/dockerfile:1.7

ARG PYTHON_BASE_IMAGE=python:3.14-slim-trixie
ARG TERRAFORM_VERSION=1.14.9
ARG TERRAMATE_VERSION=0.17.0
ARG VULTR_CLI_VERSION=3.10.0

FROM ${PYTHON_BASE_IMAGE} AS base

ARG TARGETARCH
ARG TERRAFORM_VERSION
ARG TERRAMATE_VERSION

ENV DEBIAN_FRONTEND=noninteractive
ENV EVE_HOME=/data
ENV PATH="/root/.local/bin:/usr/local/bin:${PATH}"
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VIRTUALENVS_CREATE=false

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    gnupg \
    jq \
    make \
    openssh-client \
    shellcheck \
    sshpass \
    unzip \
    xz-utils \
    yq \
  && python3 -m pip install --no-cache-dir poetry \
  && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
  case "${TARGETARCH}" in \
    amd64|x86_64) terraform_arch=amd64; terramate_arch=x86_64 ;; \
    arm64|aarch64) terraform_arch=arm64; terramate_arch=arm64 ;; \
    *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
  esac; \
  curl -fsSLo /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${terraform_arch}.zip"; \
  unzip -q -d /usr/local/bin /tmp/terraform.zip; \
  curl -fsSLo /tmp/terramate.tar.gz "https://github.com/terramate-io/terramate/releases/download/v${TERRAMATE_VERSION}/terramate_${TERRAMATE_VERSION}_linux_${terramate_arch}.tar.gz"; \
  mkdir -p /tmp/terramate; \
  tar -C /tmp/terramate -xzf /tmp/terramate.tar.gz; \
  find /tmp/terramate -type f -name terramate -exec install -m 0755 {} /usr/local/bin/terramate \; -quit; \
  test -x /usr/local/bin/terramate; \
  rm -rf /tmp/terraform.zip /tmp/terramate /tmp/terramate.tar.gz

FROM base AS app-deps

WORKDIR /opt/eve
COPY . /opt/eve

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential \
  && git init -q \
  && git config user.email eve-container@example.invalid \
  && git config user.name "Eve Container" \
  && git add . \
  && git commit -q -m "docker image snapshot" \
  && poetry install --only main --no-interaction --no-root \
  && apt-get purge -y --auto-remove build-essential \
  && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* \
  && find /usr/local/lib/python3.14 -depth -name __pycache__ -prune -exec rm -rf {} + \
  && find /usr/local/lib/python3.14 -type f -name '*.pyc' -delete \
  && find /usr/local/lib/python3.14 -type f -name '*.a' -delete \
  && rm -rf \
    /usr/local/include/python3.14 \
    /usr/local/lib/python3.14/idlelib \
    /usr/local/lib/python3.14/test \
    /usr/local/lib/python3.14/tkinter

FROM app-deps AS runtime-base

COPY docker/entrypoint.sh /usr/local/bin/eve-entrypoint
ENTRYPOINT ["/usr/local/bin/eve-entrypoint"]
CMD ["make", "eve"]

FROM runtime-base AS runtime-slim

ARG TARGETARCH
ARG VULTR_CLI_VERSION

RUN set -eux; \
  case "${TARGETARCH}" in \
    amd64|x86_64) tool_arch=amd64 ;; \
    arm64|aarch64) tool_arch=arm64 ;; \
    *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
  esac; \
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg; \
  printf '%s\n' "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" > /etc/apt/sources.list.d/google-cloud-sdk.list; \
  apt-get update; \
  apt-get install -y --no-install-recommends google-cloud-cli; \
  python3 -m pip install --no-cache-dir awscli; \
  curl -fsSLo /tmp/vultr-cli.tar.gz "https://github.com/vultr/vultr-cli/releases/download/v${VULTR_CLI_VERSION}/vultr-cli_v${VULTR_CLI_VERSION}_linux_${tool_arch}.tar.gz"; \
  mkdir -p /tmp/vultr-cli; \
  tar -C /tmp/vultr-cli -xzf /tmp/vultr-cli.tar.gz; \
  find /tmp/vultr-cli -type f -name vultr-cli -exec install -m 0755 {} /usr/local/bin/vultr-cli \; -quit; \
  test -x /usr/local/bin/vultr-cli; \
  rm -rf \
    /tmp/vultr-cli \
    /tmp/vultr-cli.tar.gz \
    /usr/lib/google-cloud-sdk/platform/bq \
    /usr/lib/google-cloud-sdk/platform/gsutil \
    /usr/share/doc/* \
    /usr/share/man/* \
    /var/cache/apt/archives/* \
    /var/lib/apt/lists/*; \
  find /usr/lib/google-cloud-sdk /usr/local/lib/python3.14 -depth -name __pycache__ -prune -exec rm -rf {} +; \
  find /usr/lib/google-cloud-sdk /usr/local/lib/python3.14 -type f -name '*.pyc' -delete

FROM runtime-slim AS runtime-full

# qemu-system-arm provides qemu-system-aarch64; full is the local QEMU/Vagrant variant.
RUN set -eux; \
  case "$(dpkg --print-architecture)" in \
    amd64) ;; \
    *) echo "runtime-full requires linux/amd64 because HashiCorp does not publish a Vagrant apt package for this architecture" >&2; exit 1 ;; \
  esac; \
  . /etc/os-release; \
  curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg; \
  printf '%s\n' "deb [arch=amd64 signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${VERSION_CODENAME} main" > /etc/apt/sources.list.d/hashicorp.list; \
  apt-get update; \
  apt-get install -y --no-install-recommends \
    qemu-system-arm \
    qemu-system-x86 \
    vagrant \
  && rm -rf /usr/share/doc/* /usr/share/man/* /var/cache/apt/archives/* /var/lib/apt/lists/*
