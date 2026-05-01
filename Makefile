# Makefile
.DEFAULT_GOAL := default
.PHONY: all aws.login clean default down env generate help info \
				init init.all instance.create instance.env instance.info \
				instance.list instance.validate ip lint logs plan \
				profiles.list profiles.menu providers.status provision \
				recipes.list \
				provision.clear-state provision.restart provision.wait reboot \
				remote.console remote.moonlight remote.moonlight.pair \
				remote.rdp remote.rustdesk remote.rustdesk.info \
				remote.sunshine remote.sunshine.wait \
				remote.vnc remote.xpra remote.xpra.apps remote.xpra.attach \
				remote.xpra.desktop remote.xpra.run remote.xpra.start remote.xpra.status \
				remote.xpra.stop \
				show-password ssh ssh.run ssh.truenas ssh.wait start status stop \
				test test.instances test.profiles test.shellcheck test.terraform \
				test.update-golden up update upload validate

TM_PARALLEL ?= 8

# Profile selection: set PROFILE= explicitly, or run `make profiles.menu` to pick
# one. If PROFILE is unset, interactive targets will prompt.
PROFILE ?=

# v3 concrete instance selection. Instances live in .egame/instances.yaml.
INSTANCE ?=
export INSTANCE

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

down: ## Destroy profile resources (terraform or vagrant)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate; \
	ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
	if [ "$$ENGINE" = "vagrant" ]; then \
		./scripts/vagrant-destroy $(PROFILE); \
	elif [ "$$ENGINE" = "metal" ]; then \
		echo "[down] PROFILE=$(PROFILE) is metal hardware; nothing to destroy."; \
	else \
		./scripts/tf-destroy $(PROFILE); \
	fi

env: ## Print resolved profile data as env lines
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --emit env

generate: ## Generate terraform configuration from terramate files
	terramate generate

help: ## Show this help message
	@echo 'v3: Instance-Driven VM Platform'
	@echo
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[$$()% a-zA-Z_.-]+:.*?##/ { printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2 } ' $(MAKEFILE_LIST)

info: ## Print resolved profile data as JSON
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --emit json

init: ## Initialize profile backend/providers (terraform only)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate; \
	ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
	if [ "$$ENGINE" = "metal" ]; then \
		echo "[init] PROFILE=$(PROFILE) is metal hardware; no Terraform backend to initialize."; \
	else \
		./scripts/tf-init $(PROFILE); \
	fi

init.all: generate ## Init all stacks in parallel (set TM_PARALLEL=N)
	terramate run --parallel=$(TM_PARALLEL) --continue-on-error -- terraform init -upgrade

instance.create: ## Create a local instance registry entry (NAME=<name> RECIPE=<recipe>)
	@if [ -z "$(NAME)" ] || [ -z "$(RECIPE)" ]; then echo "Usage: make instance.create NAME=<name> RECIPE=<recipe> [BUNDLES=a,b] [DISK_GB=n] [MEMORY_MB=n]"; exit 2; fi; \
	args="--name $(NAME) --recipe $(RECIPE)"; \
	if [ -n "$(MACHINE)" ]; then args="$$args --machine $(MACHINE)"; fi; \
	if [ -n "$(OS)" ]; then args="$$args --os $(OS)"; fi; \
	if [ -n "$(INIT)" ]; then args="$$args --init $(INIT)"; fi; \
	if [ -n "$(LOCATION)" ]; then args="$$args --location $(LOCATION)"; fi; \
	if [ -n "$(BUNDLES)" ]; then args="$$args --bundles $(BUNDLES)"; fi; \
	if [ -n "$(DISK_GB)" ]; then args="$$args --disk-gb $(DISK_GB)"; fi; \
	if [ -n "$(MEMORY_MB)" ]; then args="$$args --memory-mb $(MEMORY_MB)"; fi; \
	if [ -n "$(CPU_CORES)" ]; then args="$$args --cpu-cores $(CPU_CORES)"; fi; \
	if [ -n "$(VCPUS)" ]; then args="$$args --vcpus $(VCPUS)"; fi; \
	if [ -n "$(INSTANCE_TYPE)" ]; then args="$$args --instance-type $(INSTANCE_TYPE)"; fi; \
	if [ -n "$(ROOT_VOLUME_TYPE)" ]; then args="$$args --root-volume-type $(ROOT_VOLUME_TYPE)"; fi; \
	if [ -n "$(PLAN)" ]; then args="$$args --plan $(PLAN)"; fi; \
	./scripts/instance-create $$args

instance.env: ## Print resolved concrete instance data as env lines
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.env INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-resolve --instance $(INSTANCE) --emit env

instance.info: ## Print resolved concrete instance data as JSON
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.info INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-resolve --instance $(INSTANCE) --emit json | jq .

instance.list: ## List local concrete instances
	@./scripts/instance-list

instance.validate: ## Validate a concrete instance from .egame/instances.yaml
	@if [ -z "$(INSTANCE)" ]; then echo "Usage: make instance.validate INSTANCE=<name>"; exit 2; fi; \
	./scripts/instance-resolve --instance $(INSTANCE) --validate

ip: ## Print the instance IP for a profile
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/instance-ip $(PROFILE)

lint: ## Format terramate files in place
	terramate fmt

logs: ## Stream the remote provisioning logs for a profile (OS-aware)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/logs $(PROFILE)

plan: ## Plan profile changes (terraform or vagrant)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate; \
	ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
	if [ "$$ENGINE" = "vagrant" ]; then \
		./scripts/vagrant-up --plan $(PROFILE); \
	elif [ "$$ENGINE" = "metal" ]; then \
		echo "[plan] PROFILE=$(PROFILE) is metal hardware; provisioning will run over SSH."; \
		./scripts/profile-resolve --profile $(PROFILE) --emit env; \
	else \
		./scripts/tf-plan $(PROFILE); \
	fi

profiles.list: ## List available profiles with details
	@./scripts/profiles-list --with-details

profiles.menu: ## Interactive profile selector
	@./scripts/profile-menu

providers.status: ## Check provider configuration and connectivity
	@./scripts/providers-status

recipes.list: ## List reusable VM recipes
	@./scripts/recipes-list --with-details

provision: ## Upload and run OS-appropriate provisioning scripts on the instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/provision $(PROFILE)

provision.clear-state: ## Clear remote provisioning state, logs, and downloads
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	OS_FAMILY=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^OS_FAMILY=/{print $$2}'); \
	case "$$OS_FAMILY" in \
		ubuntu) ./scripts/instance-ssh $(PROFILE) -- 'rm -rf ~/provision/state ~/provision/logs ~/provision/downloads' ;; \
		windows) ./scripts/instance-ssh $(PROFILE) -- 'if (Test-Path "C:\Users\Administrator\provision\state") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\state" }; if (Test-Path "C:\Users\Administrator\provision\logs") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\logs" }; if (Test-Path "C:\Users\Administrator\provision\downloads") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\downloads" }' ;; \
		*) echo "[provision.clear-state] unknown os_family: $$OS_FAMILY" >&2; exit 2 ;; \
	esac

provision.restart: provision.clear-state provision ## Clear remote state then re-provision

provision.wait: ## Wait until provisioning finishes (survives intermediate reboots)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/wait-for-provision $(PROFILE)

update: ## Update all installed tools to latest versions
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/update-tools $(PROFILE)

reboot: ## Reboot the instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	OS_FAMILY=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^OS_FAMILY=/{print $$2}'); \
	case "$$OS_FAMILY" in \
		windows) ./scripts/instance-ssh $(PROFILE) -- 'shutdown /r /t 0' ;; \
		*) ./scripts/instance-ssh $(PROFILE) -- 'sudo reboot' ;; \
	esac

remote.console: ## Open the VM's graphical console (VMware Fusion / VirtualBox)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-console $(PROFILE)

remote.moonlight: remote.sunshine.wait ## Start Moonlight stream
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-moonlight $(PROFILE)

remote.moonlight.pair: remote.sunshine.wait ## Pair Moonlight with Sunshine via a fixed PIN
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-moonlight-pair $(PROFILE)

remote.rdp: ## Open RDP session to Windows instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-rdp $(PROFILE)

remote.rustdesk: ## Open local RustDesk client connected to the instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-rustdesk $(PROFILE) connect

remote.rustdesk.info: ## Print RustDesk connection details (ID, password, server)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-rustdesk $(PROFILE)

remote.sunshine: ## Open the Sunshine web UI for the instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	IP=$$(./scripts/instance-ip $(PROFILE)); \
	open "https://$$IP:47990" || open -a "Google Chrome" "https://$$IP:47990"

remote.sunshine.wait: ## Wait until the Sunshine API accepts authenticated requests
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-sunshine-wait $(PROFILE)

remote.vnc: ## Open VNC viewer to the VM (requires vnc package in profile)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-vnc $(PROFILE)

remote.xpra: ## Start server, launch app, and attach (requires APP=<cmd>)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	if [ -z "$(APP)" ]; then echo "Usage: make remote.xpra PROFILE=<name> APP=<command>"; exit 2; fi; \
	./scripts/remote-xpra $(PROFILE) start && \
	./scripts/remote-xpra $(PROFILE) run $(APP) && \
	./scripts/remote-xpra $(PROFILE) attach

remote.xpra.apps: ## List available GUI apps on the remote instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-xpra $(PROFILE) apps

remote.xpra.attach: ## Attach local xpra client to the running session
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-xpra $(PROFILE) attach

remote.xpra.desktop: ## Start and attach an Xpra full desktop session
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-xpra $(PROFILE) desktop

remote.xpra.run: ## Run an additional app on the existing Xpra session (requires APP=<cmd>)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	if [ -z "$(APP)" ]; then echo "Usage: make remote.xpra.run PROFILE=<name> APP=<command>"; exit 2; fi; \
	./scripts/remote-xpra $(PROFILE) run $(APP)

remote.xpra.start: ## Start the xpra server on the remote
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-xpra $(PROFILE) start

remote.xpra.status: ## Show xpra server status
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-xpra $(PROFILE) status

remote.xpra.stop: ## Stop the remote xpra server
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/remote-xpra $(PROFILE) stop

show-password: ## Display the instance's default password (Windows)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/instance-password $(PROFILE)

ssh: ## SSH into the profile's instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/instance-ssh $(PROFILE)

ssh.run: ## Run a remote command on the profile's instance (command read from stdin)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	if [ -t 0 ]; then echo "Usage: echo '<command>' | make ssh.run PROFILE=<name>"; exit 2; fi; \
	cmd=$$(cat); \
	./scripts/instance-ssh $(PROFILE) -- "$$cmd"

ssh.truenas: ## SSH directly into the TrueNAS host (no profile needed)
	@./scripts/env-require TRUENAS_HOST TRUENAS_SSH_USER; \
	opts="-o StrictHostKeyChecking=no -o IdentitiesOnly=yes"; \
	if [ -n "$$TRUENAS_SSH_PRIVATE_KEY_FILE" ]; then opts="$$opts -i $$TRUENAS_SSH_PRIVATE_KEY_FILE"; fi; \
	if [ -n "$$TRUENAS_SSH_PORT" ]; then opts="$$opts -p $$TRUENAS_SSH_PORT"; fi; \
	exec ssh $$opts "$${TRUENAS_SSH_USER}@$${TRUENAS_HOST}"

ssh.wait: ## Wait until SSH on the profile's instance accepts connections
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/ssh-wait $(PROFILE)

start: up ## Start (power on) a stopped instance (runs up first if not created)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/start $(PROFILE)

status: ## Show VM status (running/stopped/not created) and IP
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/status $(PROFILE)

stop: ## Stop (power off) a running instance without destroying
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/stop $(PROFILE)

test: ## Run all tests (profiles, instances, terraform validate, shellcheck)
	@./scripts/test

test.instances: ## Validate fixture instances and compare emitted env to golden snapshots
	@./scripts/test-instances

test.profiles: ## Validate all profiles and compare emitted env to golden snapshots
	@./scripts/test-profiles

test.shellcheck: ## Run shellcheck over scripts/ and linux/provision/
	@./scripts/test-shellcheck

test.terraform: ## terramate generate + terraform validate across provider stacks
	@./scripts/test-terraform

test.update-golden: ## Regenerate tests/golden/*.env from current profile-resolve output
	@UPDATE_GOLDEN=1 ./scripts/test-profiles
	@UPDATE_GOLDEN=1 ./scripts/test-instances

up: ## Create and start profile resources (terraform or vagrant)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate; \
	ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
	if [ "$$ENGINE" = "vagrant" ]; then \
		./scripts/vagrant-up $(PROFILE); \
	elif [ "$$ENGINE" = "metal" ]; then \
		echo "[up] PROFILE=$(PROFILE) is metal hardware; nothing to create."; \
	else \
		./scripts/tf-apply $(PROFILE); \
	fi

upload: ## scp ./upload/* to the instance (skips files that already exist remotely)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/upload $(PROFILE)

validate: ## Validate a profile from config/catalog.yaml
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate
