# Makefile
.DEFAULT_GOAL := default
.PHONY: ai.sandbox all aws.login catalog.list clean default doctor down env generate help info integration.plan integration.test \
				init init.all instance.create instance.delete instance.env instance.info instance.provision \
				instance.list instance.paths instance.recover instance.state instance.status instance.validate ip lint logs plan \
				package.action package.down package.install package.list package.reinstall package.select \
				package.status package.uninstall package.unselect \
				plugins.list plugins.sync plugins.validate \
				provider.status providers.status provision \
				provision.clear-state provision.restart provision.wait reboot \
				remote.console remote.moonlight remote.moonlight.pair \
				remote.rdp remote.rustdesk remote.rustdesk.info remote.waypipe \
				remote.sunshine remote.sunshine.wait \
				remote.vnc remote.xpra remote.xpra.apps remote.xpra.attach \
				remote.xpra.desktop remote.xpra.run remote.xpra.start remote.xpra.status \
				remote.xpra.stop \
				show-password ssh ssh.run ssh.truenas ssh.wait start status stop \
				test test.catalog test.instances test.plugins test.plugins-sync test.python test.shellcheck test.terraform \
				test.lint test.tf-isolation test.tui test.update-golden tui up update upload validate

TM_PARALLEL ?= 8
AGENT ?= codex

# v3 concrete instance selection. Instances live in .egame/instances.yaml.
INSTANCE ?=
export INSTANCE

# Output format for small inspection helpers.
EMIT ?= env

# Load dotenv files
-include .env
-include .env.local

# TIMEZONE is the only "documented in .env" variable that defaults instead of
# erroring when unset: fall back to the host's configured timezone.
ifeq ($(strip $(TIMEZONE)),)
TIMEZONE := $(shell readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')
endif

export AWS_CONFIG_FILE
export AWS_PROFILE
export AWS_REGION
export AWS_SHARED_CREDENTIALS_FILE
export EPHEMERAL_DISPLAY_RESOLUTION
export EPHEMERAL_DISPLAY_FPS
export EPHEMERAL_MOONLIGHT_BITRATE_KBPS
export EPHEMERAL_MOONLIGHT_VIDEO_CODEC
export EPHEMERAL_MOONLIGHT_VIDEO_DECODER
export EPHEMERAL_SUNSHINE_PASSWORD
export EPHEMERAL_WINDOWS_PASSWORD
export MY_IP
export RASPBERRY_PI_HOST
export RASPBERRY_PI_HDMI_CONNECTOR
export RASPBERRY_PI_HDMI_MODE
export RASPBERRY_PI_IP
export RASPBERRY_PI_USER_PASSWORD
export RUSTDESK_KEY
export RUSTDESK_PASSWORD
export RUSTDESK_SERVER
export SSH_PUBLIC_KEY_FILE
export SUNSHINE_MAX_BITRATE_KBPS
export SUNSHINE_VERSION
export TIMEZONE
export TRUENAS_API_KEY
export TRUENAS_API_USER
export TRUENAS_HOST
export TRUENAS_SSH_HOST_KEY_FINGERPRINT
export TRUENAS_SSH_PORT
export TRUENAS_SSH_PRIVATE_KEY_FILE
export TRUENAS_SSH_USER
export TRUENAS_VM_BASE_DIR
export TRUENAS_VM_POOL
export TRUENAS_VM_ZVOL_PREFIX
export VAGRANT_SHOW_CONSOLE
export VM_USER_NAME
export VULTR_API_KEY

all: init up ssh.wait provision provision.wait remote.sunshine.wait remote.moonlight.pair remote.moonlight ## Full setup: up, provision, pair Moonlight, start stream

aws.login: ## Refresh AWS CLI login session for the selected profile
	aws login --profile $(AWS_PROFILE)

clean: ## Remove terramate-generated terraform files and cache
	find stacks -name ".terraform" -type d -prune -exec rm -rf {} \;
	find stacks -name ".terraform.lock.hcl" -type f -exec rm -f {} \;
	find stacks -name "z_*.tf" -type f -exec rm -f {} \;
	rm -rf .terraform-cache-dir/data/*
	rm -rf .terraform-cache-dir/plugins/*
	rm -rf .terraform-cache-dir/state/*

default: help  ## Show help

doctor: ## Check local tools, plugins, providers, and state hints
	./scripts/doctor

ai.sandbox: ## Run a coding agent in Docker Sandboxes (AGENT=codex|opencode|claude|shell)
	@if ! command -v sbx >/dev/null 2>&1; then \
		echo "Docker Sandboxes CLI (sbx) is not installed."; \
		echo "See docs/ai-sandboxes.md for setup notes."; \
		exit 2; \
	fi; \
	exec sbx run $(AGENT) .

down: ## Destroy provider resources for an instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make down INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run down $(INSTANCE)

env: ## Print resolved instance data as env lines
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make env INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run env $(INSTANCE)

generate: ## Generate terraform configuration from terramate files
	terramate generate

help: ## Show this help message
	@echo 'v3: Instance-Driven VM Platform'
	@echo
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[$$()% a-zA-Z_.-]+:.*?##/ { printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2 } ' $(MAKEFILE_LIST)

info: ## Print resolved instance data as JSON
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make info INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run info $(INSTANCE)

integration.plan: ## Print integration test plan (INSTANCES=a,b)
	@if [ -z "$(INSTANCES)" ]; then echo "Usage: make integration.plan INSTANCES=<linux>,<windows>"; exit 2; fi; \
	args=""; \
	for instance in $$(printf '%s' "$(INSTANCES)" | tr ',' ' '); do args="$$args --instance $$instance"; done; \
	./scripts/integration-test $$args

integration.test: ## Run live integration test (INSTANCES=a,b YES=1 DELETE_INSTANCES=1)
	@if [ -z "$(INSTANCES)" ]; then echo "Usage: make integration.test INSTANCES=<linux>,<windows> YES=1"; exit 2; fi; \
	args=""; \
	for instance in $$(printf '%s' "$(INSTANCES)" | tr ',' ' '); do args="$$args --instance $$instance"; done; \
	if [ "$(DELETE_INSTANCES)" = "1" ]; then args="$$args --delete-instances"; fi; \
	./scripts/integration-test --live $$args

init: ## Initialize provider backend for an instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make init INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run init $(INSTANCE)

init.all: generate ## Init all stacks in parallel (set TM_PARALLEL=N)
	terramate run --parallel=$(TM_PARALLEL) --continue-on-error -- terraform init -upgrade

instance.create: ## Create a local instance registry entry (INSTANCE=<name> MACHINE=... OS=... LOCATION=...)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.create INSTANCE=<name> MACHINE=<machine> OS=<os> LOCATION=<location> [INIT=<init>] [BUNDLES=a,b] [PACKAGES=a,b] [DISK_GB=n] [MEMORY_MB=n]"; exit 2; fi; \
	args="--instance $(INSTANCE)"; \
	if [ -n "$(MACHINE)" ]; then args="$$args --machine $(MACHINE)"; fi; \
	if [ -n "$(OS)" ]; then args="$$args --os $(OS)"; fi; \
	if [ -n "$(INIT)" ]; then args="$$args --init $(INIT)"; fi; \
	if [ -n "$(LOCATION)" ]; then args="$$args --location $(LOCATION)"; fi; \
	if [ -n "$(BUNDLES)" ]; then args="$$args --bundles $(BUNDLES)"; fi; \
	if [ -n "$(PACKAGES)" ]; then args="$$args --packages $(PACKAGES)"; fi; \
	if [ -n "$(DISK_GB)" ]; then args="$$args --disk-gb $(DISK_GB)"; fi; \
	if [ -n "$(MEMORY_MB)" ]; then args="$$args --memory-mb $(MEMORY_MB)"; fi; \
	if [ -n "$(CPU_CORES)" ]; then args="$$args --cpu-cores $(CPU_CORES)"; fi; \
	if [ -n "$(VCPUS)" ]; then args="$$args --vcpus $(VCPUS)"; fi; \
	if [ -n "$(INSTANCE_TYPE)" ]; then args="$$args --instance-type $(INSTANCE_TYPE)"; fi; \
	if [ -n "$(ROOT_VOLUME_TYPE)" ]; then args="$$args --root-volume-type $(ROOT_VOLUME_TYPE)"; fi; \
	if [ -n "$(PLAN)" ]; then args="$$args --plan $(PLAN)"; fi; \
	./scripts/instance-create $$args

instance.delete: ## Delete a local instance registry entry (INSTANCE=<name>, PURGE=1 to remove generated files)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.delete INSTANCE=<name> [PURGE=1]"; exit 2; fi; \
	args="--instance $(INSTANCE)"; \
	if [ "$(PURGE)" = "1" ]; then args="$$args --purge"; fi; \
	./scripts/instance-delete $$args

instance.env: ## Print resolved concrete instance data as env lines
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.env INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-resolve --instance $(INSTANCE) --emit env

instance.info: ## Print resolved concrete instance data as JSON
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.info INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-resolve --instance $(INSTANCE) --emit json | jq .

instance.list: ## List local concrete instances
	@./scripts/instance-list

instance.paths: ## Print resolved local artifact paths for an instance (EMIT=env|json)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.paths INSTANCE=<name> [EMIT=env|json]"; exit 2; fi; \
	./scripts/instance-paths --instance $(INSTANCE) --emit $(EMIT)

instance.provision: ## Converge provisioning for an instance (FORCE=1 clears remote provision state first)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.provision INSTANCE=<name> [FORCE=1]"; exit 2; fi; \
	args="--instance $(INSTANCE)"; \
	if [ "$(FORCE)" = "1" ]; then args="$$args --force"; fi; \
	./scripts/instance-provision $$args

instance.recover: ## Mark an interrupted running operation as failed
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.recover INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-state --instance $(INSTANCE) --recover-running | jq .

instance.state: ## Print local orchestration state for an instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.state INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-state --instance $(INSTANCE) --get | jq .

instance.status: ## Print combined resolved metadata, local state, packages, and paths
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.status INSTANCE=<name> [EMIT=json]"; exit 2; fi; \
	args="--instance $(INSTANCE)"; \
	if [ "$(EMIT)" = "json" ]; then args="$$args --json"; fi; \
	./scripts/instance-status $$args

instance.validate: ## Validate a concrete instance from .egame/instances.yaml
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.validate INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-resolve --instance $(INSTANCE) --validate

ip: ## Print the instance IP
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make ip INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run ip $(INSTANCE)

lint: ## Format terramate files in place
	terramate fmt

logs: ## Stream remote provisioning logs for an instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make logs INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run logs $(INSTANCE)

plan: ## Plan provider changes for an instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make plan INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run plan $(INSTANCE)

package.action: ## Run a package-defined action (PACKAGE=<id> ACTION=<id>)
	@if [ -z "$(INSTANCE)" ] || [ -z "$(PACKAGE)" ] || [ -z "$(ACTION)" ]; then echo "Usage: make package.action INSTANCE=<name> PACKAGE=<id> ACTION=<id>"; exit 2; fi; \
	./scripts/package-action --instance $(INSTANCE) --package $(PACKAGE) --action $(ACTION)

package.down: ## Remove package from an instance (PACKAGE=<id>, YES=1 for destructive)
	@if [ -z "$(INSTANCE)" ] || [ -z "$(PACKAGE)" ]; then echo "Usage: make package.down INSTANCE=<name> PACKAGE=<id> YES=1"; exit 2; fi; \
	args="--instance $(INSTANCE) --package $(PACKAGE) --command down"; \
	if [ "$(YES)" = "1" ]; then args="$$args --yes"; fi; \
	./scripts/package-dispatch $$args

package.uninstall: package.down ## Alias for package.down

package.install: ## Install selected package set for an instance (PACKAGE=<id>)
	@if [ -z "$(INSTANCE)" ] || [ -z "$(PACKAGE)" ]; then echo "Usage: make package.install INSTANCE=<name> PACKAGE=<id>"; exit 2; fi; \
	./scripts/package-dispatch --instance $(INSTANCE) --package $(PACKAGE) --command install

package.list: ## List package plugins for an instance with selection/support
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make package.list INSTANCE=<name> [EMIT=json]"; exit 2; fi; \
	args="--instance $(INSTANCE)"; \
	if [ "$(EMIT)" = "json" ]; then args="$$args --json"; fi; \
	./scripts/package-list $$args

package.reinstall: ## Reinstall package on an instance (PACKAGE=<id>, YES=1 for destructive)
	@if [ -z "$(INSTANCE)" ] || [ -z "$(PACKAGE)" ]; then echo "Usage: make package.reinstall INSTANCE=<name> PACKAGE=<id> YES=1"; exit 2; fi; \
	args="--instance $(INSTANCE) --package $(PACKAGE) --command reinstall"; \
	if [ "$(YES)" = "1" ]; then args="$$args --yes"; fi; \
	./scripts/package-dispatch $$args

package.select: ## Add a package to an instance's desired package list
	@if [ -z "$(INSTANCE)" ] || [ -z "$(PACKAGE)" ]; then echo "Usage: make package.select INSTANCE=<name> PACKAGE=<id>"; exit 2; fi; \
	./scripts/package-selection --instance $(INSTANCE) --package $(PACKAGE) --add

package.status: ## Show package plugin status for an instance (PACKAGE=<id>)
	@if [ -z "$(INSTANCE)" ] || [ -z "$(PACKAGE)" ]; then echo "Usage: make package.status INSTANCE=<name> PACKAGE=<id>"; exit 2; fi; \
	./scripts/package-dispatch --instance $(INSTANCE) --package $(PACKAGE) --command status

package.unselect: ## Remove a package from an instance's desired direct package list
	@if [ -z "$(INSTANCE)" ] || [ -z "$(PACKAGE)" ]; then echo "Usage: make package.unselect INSTANCE=<name> PACKAGE=<id>"; exit 2; fi; \
	./scripts/package-selection --instance $(INSTANCE) --package $(PACKAGE) --remove

plugins.list: ## List provider and package plugins
	@./scripts/plugin-list

plugins.sync: ## Download pinned external plugins from .egame/plugin-sources.yaml
	@./scripts/plugins-sync

plugins.validate: ## Validate provider and package plugin manifests
	@./scripts/plugin-list --validate

provider.status: ## Show provider plugin status for an instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make provider.status INSTANCE=<name>"; exit 2; fi; \
	./scripts/provider-dispatch --instance $(INSTANCE) --command status

providers.status: ## Check provider configuration and connectivity
	@./scripts/providers-status

catalog.list: ## List provider/platform/content choices
	@./scripts/catalog-options

provision: ## Upload and run OS-appropriate provisioning scripts on the instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make provision INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run provision $(INSTANCE)

provision.clear-state: ## Clear remote provisioning state, logs, and downloads
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make provision.clear-state INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run provision.clear-state $(INSTANCE)

provision.restart: provision.clear-state provision ## Clear remote state then re-provision

provision.wait: ## Wait until provisioning finishes (survives intermediate reboots)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make provision.wait INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run provision.wait $(INSTANCE)

update: ## Update all installed tools to latest versions
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make update INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run update $(INSTANCE)

reboot: ## Reboot the instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make reboot INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run reboot $(INSTANCE)

remote.console: ## Open the VM's graphical console (VMware Fusion / VirtualBox)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.console INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.console $(INSTANCE)

remote.moonlight: remote.sunshine.wait ## Start Moonlight stream
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.moonlight INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.moonlight $(INSTANCE)

remote.moonlight.pair: remote.sunshine.wait ## Pair Moonlight with Sunshine via a fixed PIN
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.moonlight.pair INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.moonlight.pair $(INSTANCE)

remote.rdp: ## Open RDP session to Windows instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.rdp INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.rdp $(INSTANCE)

remote.rustdesk: ## Open local RustDesk client connected to the instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.rustdesk INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.rustdesk $(INSTANCE)

remote.rustdesk.info: ## Print RustDesk connection details (ID, password, server)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.rustdesk.info INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.rustdesk.info $(INSTANCE)

remote.sunshine: ## Open the Sunshine web UI for the instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.sunshine INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.sunshine $(INSTANCE)

remote.sunshine.wait: ## Wait until the Sunshine API accepts authenticated requests
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.sunshine.wait INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.sunshine.wait $(INSTANCE)

remote.vnc: ## Open VNC viewer to the VM (requires vnc package in profile)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.vnc INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.vnc $(INSTANCE)

remote.waypipe: ## Run a remote Wayland app through waypipe (APP='foot' by default)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.waypipe INSTANCE=<name> [APP=<command>]"; exit 2; fi; \
	./scripts/instance-run remote.waypipe $(INSTANCE)

remote.xpra: ## Start server, launch app, and attach (requires APP=<cmd>)
	@if [ -z "$(INSTANCE)" ] || [ -z "$(APP)" ]; then echo "Usage: make remote.xpra INSTANCE=<name> APP=<command>"; exit 2; fi; \
	./scripts/instance-run remote.xpra $(INSTANCE)

remote.xpra.apps: ## List available GUI apps on the remote instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.xpra.apps INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.xpra.apps $(INSTANCE)

remote.xpra.attach: ## Attach local xpra client to the running session
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.xpra.attach INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.xpra.attach $(INSTANCE)

remote.xpra.desktop: ## Start and attach an Xpra full desktop session
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.xpra.desktop INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.xpra.desktop $(INSTANCE)

remote.xpra.run: ## Run an additional app on the existing Xpra session (requires APP=<cmd>)
	@if [ -z "$(INSTANCE)" ] || [ -z "$(APP)" ]; then echo "Usage: make remote.xpra.run INSTANCE=<name> APP=<command>"; exit 2; fi; \
	./scripts/instance-run remote.xpra.run $(INSTANCE)

remote.xpra.start: ## Start the xpra server on the remote
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.xpra.start INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.xpra.start $(INSTANCE)

remote.xpra.status: ## Show xpra server status
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.xpra.status INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.xpra.status $(INSTANCE)

remote.xpra.stop: ## Stop the remote xpra server
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make remote.xpra.stop INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run remote.xpra.stop $(INSTANCE)

show-password: ## Display the instance's default password (Windows)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make show-password INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run show-password $(INSTANCE)

ssh: ## SSH into the instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make ssh INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run ssh $(INSTANCE)

ssh.run: ## Run a remote command on the instance (command read from stdin)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: echo '<command>' | make ssh.run INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run ssh.run $(INSTANCE)

ssh.truenas: ## SSH directly into the TrueNAS host (no profile needed)
	@./scripts/env-require TRUENAS_HOST TRUENAS_SSH_USER; \
	opts="-o StrictHostKeyChecking=no -o IdentitiesOnly=yes"; \
	if [ -n "$$TRUENAS_SSH_PRIVATE_KEY_FILE" ]; then opts="$$opts -i $$TRUENAS_SSH_PRIVATE_KEY_FILE"; fi; \
	if [ -n "$$TRUENAS_SSH_PORT" ]; then opts="$$opts -p $$TRUENAS_SSH_PORT"; fi; \
	exec ssh $$opts "$${TRUENAS_SSH_USER}@$${TRUENAS_HOST}"

ssh.wait: ## Wait until SSH on the instance accepts connections
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make ssh.wait INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run ssh.wait $(INSTANCE)

start: ## Start (power on) a stopped instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make start INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run start $(INSTANCE)

status: ## Show VM status (running/stopped/not created) and IP
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make status INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run status $(INSTANCE)

stop: ## Stop (power off) a running instance without destroying
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make stop INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run stop $(INSTANCE)

test: ## Run all tests (catalog, instances, plugins, terraform, lint)
	@./scripts/test

test.catalog: ## Validate catalog provider/platform/content choices
	@./scripts/test-catalog

test.instances: ## Validate fixture instances and compare emitted env to golden snapshots
	@./scripts/test-instances

test.lint: ## Run non-Python language lint and syntax checks
	@./scripts/test-lint

test.plugins: ## Validate plugin manifests and dry-run dispatch contracts
	@./scripts/test-plugins

test.plugins-sync: ## Validate external plugin synchronization
	@./scripts/test-plugins-sync

test.python: ## Run Python lint and type checks
	@./scripts/test-python

test.shellcheck: ## Run shellcheck over scripts/ and linux/provision/
	@./scripts/test-shellcheck

test.terraform: ## terramate generate + terraform validate across provider stacks
	@./scripts/test-terraform

test.tf-isolation: ## Verify per-instance Terraform workspace isolation in tf-* scripts
	@./scripts/test-tf-isolation

test.tui: ## Validate optional Textual TUI entrypoint
	@./scripts/test-tui

test.update-golden: ## Regenerate tests/golden/instances/*.env from current instance output
	@UPDATE_GOLDEN=1 ./scripts/test-instances

tui: ## Open the v3 Textual instance manager
	@poetry run python ./scripts/egame-tui

up: ## Create and start provider resources for an instance
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make up INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run up $(INSTANCE)

upload: ## scp ./upload/* to the instance (skips files that already exist remotely)
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make upload INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run upload $(INSTANCE)

validate: ## Validate an instance from .egame/instances.yaml
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make validate INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-run validate $(INSTANCE)
