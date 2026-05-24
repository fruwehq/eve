# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.13.13
ARG RUBY_VERSION=3.4.7
ARG TERRAFORM_VERSION=1.14.9
ARG TERRAMATE_VERSION=0.17.0
ARG VULTR_CLI_VERSION=3.10.0

FROM ubuntu:24.04 AS language-build

ARG PYTHON_VERSION
ARG RUBY_VERSION

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    autoconf \
    bison \
    build-essential \
    ca-certificates \
    curl \
    libdb-dev \
    libffi-dev \
    libgdbm-dev \
    libgmp-dev \
    libncurses-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    libyaml-dev \
    make \
    tk-dev \
    uuid-dev \
    xz-utils \
    zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
  curl -fsSLo /tmp/ruby.tar.gz "https://cache.ruby-lang.org/pub/ruby/3.4/ruby-${RUBY_VERSION}.tar.gz"; \
  mkdir -p /tmp/ruby; \
  tar -C /tmp/ruby --strip-components=1 -xzf /tmp/ruby.tar.gz; \
  cd /tmp/ruby; \
  ./configure --prefix=/opt/ruby --disable-install-doc; \
  make -j"$(nproc)"; \
  make install; \
  rm -rf /tmp/ruby /tmp/ruby.tar.gz

RUN set -eux; \
  curl -fsSLo /tmp/python.tgz "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"; \
  mkdir -p /tmp/python; \
  tar -C /tmp/python --strip-components=1 -xzf /tmp/python.tgz; \
  cd /tmp/python; \
  ./configure --prefix=/opt/python --enable-shared --with-ensurepip=install; \
  make -j"$(nproc)"; \
  make install; \
  rm -rf /tmp/python /tmp/python.tgz

FROM ubuntu:24.04 AS base

ARG TARGETARCH
ARG TERRAFORM_VERSION
ARG TERRAMATE_VERSION

ENV DEBIAN_FRONTEND=noninteractive
ENV EVE_HOME=/data
ENV LD_LIBRARY_PATH="/opt/python/lib"
ENV PATH="/opt/ruby/bin:/opt/python/bin:/root/.local/bin:/usr/local/bin:${PATH}"
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VIRTUALENVS_CREATE=false

COPY --from=language-build /opt/ruby /opt/ruby
COPY --from=language-build /opt/python /opt/python

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    gnupg \
    jq \
    libdb-dev \
    libffi-dev \
    libgdbm-dev \
    libgmp-dev \
    libncurses-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    libyaml-dev \
    make \
    openssh-client \
    shellcheck \
    sshpass \
    unzip \
    xz-utils \
    yq \
    zlib1g-dev \
  && ln -sf /opt/python/bin/python3.13 /usr/local/bin/python3 \
  && ln -sf /opt/python/bin/pip3.13 /usr/local/bin/pip3 \
  && ln -sf /opt/python/bin/python3.13 /usr/local/bin/python \
  && ln -sf /opt/python/bin/pip3.13 /usr/local/bin/pip \
  && gem install bundler -v 4.0.11 \
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

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/eve
COPY . /opt/eve

RUN bundle install \
  && poetry install --no-interaction --no-root

FROM base AS runtime-base

COPY --from=app-deps /opt/ruby /opt/ruby
COPY --from=app-deps /opt/python /opt/python
COPY --from=app-deps /opt/eve /opt/eve

WORKDIR /opt/eve
COPY docker/entrypoint.sh /usr/local/bin/eve-entrypoint
ENTRYPOINT ["/usr/local/bin/eve-entrypoint"]
CMD ["make", "eve"]

FROM runtime-base AS runtime-slim

ARG TARGETARCH
ARG VULTR_CLI_VERSION

RUN set -eux; \
  case "${TARGETARCH}" in \
    amd64|x86_64) tool_arch=amd64; aws_arch=x86_64 ;; \
    arm64|aarch64) tool_arch=arm64; aws_arch=aarch64 ;; \
    *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
  esac; \
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg; \
  printf '%s\n' "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" > /etc/apt/sources.list.d/google-cloud-sdk.list; \
  apt-get update; \
  apt-get install -y --no-install-recommends google-cloud-cli; \
  curl -fsSLo /tmp/awscliv2.zip "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip"; \
  unzip -q /tmp/awscliv2.zip -d /tmp; \
  /tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli; \
  curl -fsSLo /tmp/vultr-cli.tar.gz "https://github.com/vultr/vultr-cli/releases/download/v${VULTR_CLI_VERSION}/vultr-cli_v${VULTR_CLI_VERSION}_linux_${tool_arch}.tar.gz"; \
  mkdir -p /tmp/vultr-cli; \
  tar -C /tmp/vultr-cli -xzf /tmp/vultr-cli.tar.gz; \
  find /tmp/vultr-cli -type f -name vultr-cli -exec install -m 0755 {} /usr/local/bin/vultr-cli \; -quit; \
  test -x /usr/local/bin/vultr-cli; \
  rm -rf /var/lib/apt/lists/* /tmp/aws /tmp/awscliv2.zip /tmp/vultr-cli /tmp/vultr-cli.tar.gz

FROM runtime-slim AS runtime-full

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
  && rm -rf /var/lib/apt/lists/*
