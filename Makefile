# Makefile
.DEFAULT_GOAL := default
.PHONY: all apply aws.login clean default destroy env generate help info \
				init init.all ip lint logs plan \
				profiles.list profiles.menu providers.status provision \
				provision.clear-state provision.restart reboot \
				remote.console remote.moonlight remote.moonlight.pair \
				remote.rdp remote.sunshine remote.sunshine.wait remote.vnc remote.xpra \
				remote.xpra.start remote.xpra.attach remote.xpra.run \
				remote.xpra.stop remote.xpra.status remote.xpra.apps \
				show-password ssh ssh.wait start status stop \
				test test.profiles \
				test.shellcheck test.terraform test.update-golden tui upload \
				validate

TM_PARALLEL ?= 8

# Profile selection: set PROFILE= explicitly, or run `make profiles.menu` to pick
# one. If PROFILE is unset, interactive targets will prompt.
PROFILE ?=

# Load dotenv files
-include .env
-include .env.local

export AWS_CONFIG_FILE
export AWS_PROFILE
export AWS_REGION
export AWS_SHARED_CREDENTIALS_FILE
export EPHEMERAL_SUNSHINE_PASSWORD
export EPHEMERAL_WINDOWS_PASSWORD
export MY_IP
export SSH_PUBLIC_KEY_FILE
export TRUENAS_API_KEY
export TRUENAS_API_USER
export TRUENAS_HOST
export TRUENAS_SSH_HOST_KEY_FINGERPRINT
export TRUENAS_SSH_PORT
export TRUENAS_SSH_PRIVATE_KEY_FILE
export TRUENAS_SSH_USER
export TRUENAS_VM_ISO_DIR
export VULTR_API_KEY

all: init apply ssh.wait provision remote.sunshine.wait remote.moonlight.pair remote.moonlight ## Full setup: apply, provision, pair Moonlight, start stream

apply: ## Apply profile changes (terraform or vagrant)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate; \
	ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
	if [ "$$ENGINE" = "vagrant" ]; then \
		./scripts/vagrant-up $(PROFILE); \
	else \
		./scripts/tf-apply $(PROFILE); \
	fi

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

destroy: ## Destroy profile resources (terraform or vagrant)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate; \
	ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
	if [ "$$ENGINE" = "vagrant" ]; then \
		./scripts/vagrant-destroy $(PROFILE); \
	else \
		./scripts/tf-destroy $(PROFILE); \
	fi

env: ## Print resolved profile data as env lines
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --emit env

generate: ## Generate terraform configuration from terramate files
	terramate generate

help: ## Show this help message
	@echo 'v2: Profile-Driven VM Platform'
	@echo
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[$$()% a-zA-Z_.-]+:.*?##/ { printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2 } ' $(MAKEFILE_LIST)

info: ## Print resolved profile data as JSON
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --emit json

init: ## Initialize profile backend/providers (terraform only)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate; \
	./scripts/tf-init $(PROFILE)

init.all: generate ## Init all stacks in parallel (set TM_PARALLEL=N)
	terramate run --parallel=$(TM_PARALLEL) --continue-on-error -- terraform init -upgrade

ip: ## Print the instance IP for a profile
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-ip $(PROFILE)

lint: ## Format terramate files in place
	terramate fmt

logs: ## Stream the remote provisioning logs for a profile (OS-aware)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-logs $(PROFILE)

plan: ## Plan profile changes (terraform or vagrant)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate; \
	ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
	if [ "$$ENGINE" = "vagrant" ]; then \
		./scripts/vagrant-up --plan $(PROFILE); \
	else \
		./scripts/tf-plan $(PROFILE); \
	fi

profiles.list: ## List available profiles with details
	@./scripts/profiles-list --with-details

profiles.menu: ## Interactive profile selector
	@./scripts/profile-menu

providers.status: ## Check provider configuration and connectivity
	@./scripts/providers-status

provision: ## Upload and run OS-appropriate provisioning scripts on the instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-provision $(PROFILE)

provision.clear-state: ## Clear remote provisioning state, logs, and downloads (Windows)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-ssh $(PROFILE) -- 'if (Test-Path "C:\Users\Administrator\provision\state") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\state" }; if (Test-Path "C:\Users\Administrator\provision\logs") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\logs" }; if (Test-Path "C:\Users\Administrator\provision\downloads") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\downloads" }'

provision.restart: provision.clear-state provision ## Clear remote state then re-provision

reboot: ## Reboot the instance (Windows)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-ssh $(PROFILE) -- 'shutdown /r /t 0'

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

remote.sunshine: ## Open the Sunshine web UI for the instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	IP=$$(./scripts/profile-ip $(PROFILE)); \
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
	./scripts/profile-xpra $(PROFILE) start && \
	./scripts/profile-xpra $(PROFILE) run $(APP) && \
	./scripts/profile-xpra $(PROFILE) attach

remote.xpra.start: ## Start the xpra server on the remote
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-xpra $(PROFILE) start

remote.xpra.attach: ## Attach local xpra client to the running session
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-xpra $(PROFILE) attach

remote.xpra.run: ## Run an additional app on the existing Xpra session (requires APP=<cmd>)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	if [ -z "$(APP)" ]; then echo "Usage: make remote.xpra.run PROFILE=<name> APP=<command>"; exit 2; fi; \
	./scripts/profile-xpra $(PROFILE) run $(APP)

remote.xpra.stop: ## Stop the remote xpra server
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-xpra $(PROFILE) stop

remote.xpra.status: ## Show xpra server status
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-xpra $(PROFILE) status

remote.xpra.apps: ## List available GUI apps on the remote instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-xpra $(PROFILE) apps

show-password: ## Display the instance's default password (Windows)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-windows-password $(PROFILE)

ssh: ## SSH into the profile's instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-ssh $(PROFILE)

ssh.wait: ## Wait until SSH on the profile's instance accepts connections
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-ssh-wait $(PROFILE)

start: ## Start a stopped vagrant profile
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/vagrant-up $(PROFILE)

status: ## Show VM status (running/stopped/not created) and IP
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-status $(PROFILE)

stop: ## Stop (suspend) a running vagrant profile
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/vagrant-stop $(PROFILE)

test: ## Run all tests (profiles, terraform validate, shellcheck)
	@./scripts/test

test.profiles: ## Validate all profiles and compare emitted env to golden snapshots
	@./scripts/test-profiles

test.shellcheck: ## Run shellcheck over scripts/ and linux/provision/
	@./scripts/test-shellcheck

test.terraform: ## terramate generate + terraform validate across provider stacks
	@./scripts/test-terraform

test.update-golden: ## Regenerate tests/golden/*.env from current profile-resolve output
	@UPDATE_GOLDEN=1 ./scripts/test-profiles

tui: ## Launch the Textual profile manager
	@if [ -x ./.venv/bin/python ]; then ./.venv/bin/python ./scripts/egame-tui; else ./scripts/egame-tui; fi

upload: ## scp ./upload/* to the instance (skips files that already exist remotely)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/upload $(PROFILE)

validate: ## Validate a profile from config/catalog.yaml
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi; \
	./scripts/profile-resolve --profile $(PROFILE) --validate
