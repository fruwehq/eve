# Makefile
.DEFAULT_GOAL := default
.PHONY: all apply aws.login clean default destroy env generate help info \
				init init.all ip lint logs moonlight moonlight.pair plan \
				profiles.list profiles.menu providers.status provision \
				provision.clear-state provision.restart rdp reboot show-password \
				ssh ssh.wait sunshine sunshine.wait test test.profiles \
				test.shellcheck test.terraform test.update-golden upload \
				validate xpra

TM_PARALLEL ?= 8

# Profile selection: set PROFILE= explicitly, or run `make profiles.menu` to pick
# one. If PROFILE is unset, interactive targets will prompt.
PROFILE ?=

# Resolve instance IP and password from terraform output.
# Override with EPHEMERAL_WINDOWS_IP / EPHEMERAL_WINDOWS_PASSWORD to skip the
# terraform output call (useful when the stack state is not local).
RESOLVE_WINDOWS_IP = IP=$${EPHEMERAL_WINDOWS_IP:-$$(terramate run --tags=vultr:services:instance -- terraform output -raw vultr_instance_main_ip)}; \
	if [ -z "$$IP" ]; then echo "Missing IP"; exit 1; fi

RESOLVE_WINDOWS_PASSWORD = PW=$${EPHEMERAL_WINDOWS_PASSWORD:-$$(terramate run --tags=vultr:services:instance -- terraform output -raw vultr_instance_default_password)}; \
	if [ -z "$$PW" ]; then echo "Missing password"; exit 1; fi

# Load dotenv files
-include .env
-include .env.local

export AWS_CONFIG_FILE
export AWS_PROFILE
export AWS_REGION
export AWS_SHARED_CREDENTIALS_FILE
export EPHEMERAL_SUNSHINE_PASSWORD
export EPHEMERAL_WINDOWS_IP
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

all: init apply ssh.wait provision sunshine.wait moonlight.pair moonlight ## Full setup: apply, provision, pair Moonlight, start stream

apply: ## Apply profile changes (terraform or vagrant)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-resolve --profile $(PROFILE) --validate
	@ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
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
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-resolve --profile $(PROFILE) --validate
	@ENGINE=$$(./scripts/profile-resolve --profile $(PROFILE) --emit env | awk -F= '/^ENGINE=/{print $$2}'); \
	if [ "$$ENGINE" = "vagrant" ]; then \
		./scripts/vagrant-destroy $(PROFILE); \
	else \
		./scripts/tf-destroy $(PROFILE); \
	fi

env: ## Print resolved profile data as env lines
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-resolve --profile $(PROFILE) --emit env

generate: ## Generate terraform configuration from terramate files
	terramate generate

help: ## Show this help message
	@echo 'v2: Profile-Driven VM Platform'
	@echo
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[$$()% a-zA-Z_.-]+:.*?##/ { printf "  \033[36m%-23s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

info: ## Print resolved profile data as JSON
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-resolve --profile $(PROFILE) --emit json

init: ## Initialize profile backend/providers (terraform only)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-resolve --profile $(PROFILE) --validate
	@./scripts/tf-init $(PROFILE)

init.all: generate ## Init all stacks in parallel (set TM_PARALLEL=N)
	terramate run --parallel=$(TM_PARALLEL) --continue-on-error -- terraform init -upgrade

ip: ## Print the instance IP for a profile
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-ip $(PROFILE)

lint: ## Format terramate files in place
	terramate fmt

logs: ## Stream the remote provisioning logs for a profile (OS-aware)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-logs $(PROFILE)

moonlight: sunshine.wait ## Start Moonlight stream
	@$(RESOLVE_WINDOWS_IP); \
	/Applications/Moonlight.app/Contents/MacOS/Moonlight stream --game-optimization $$IP "Desktop"

moonlight.pair: sunshine.wait ## Pair Moonlight with Sunshine via a fixed PIN
	@$(RESOLVE_WINDOWS_IP); \
	PIN=1234; \
	PAIR_RESPONSE_FILE=./tmp/moonlight-pair-response.json; \
	mkdir -p ./tmp; \
	rm -f $$PAIR_RESPONSE_FILE; \
	printf '%s\n' "Starting Moonlight pairing against $$IP with PIN $$PIN..."; \
	/Applications/Moonlight.app/Contents/MacOS/Moonlight pair --pin $$PIN $$IP & \
	MOONLIGHT_PID=$$!; \
	sleep 2; \
	printf '%s\n' "Submitting pairing PIN to Sunshine..."; \
	HTTP_CODE=$$(curl -sS -i -k \
	  -u "sunshine:$(EPHEMERAL_SUNSHINE_PASSWORD)" \
	  -H "Content-Type: application/json" \
	  --data-binary "{\"pin\":\"$$PIN\",\"name\":\"ephemeral-client\"}" \
	  -o $$PAIR_RESPONSE_FILE \
	  -w "%{http_code}" \
	  "https://$$IP:47990/api/pin"); \
	CURL_EXIT=$$?; \
	if [ $$CURL_EXIT -ne 0 ]; then \
	  kill $$MOONLIGHT_PID >/dev/null 2>&1 || true; \
	  wait $$MOONLIGHT_PID >/dev/null 2>&1 || true; \
	  echo "Sunshine pairing API call failed."; \
	  exit $$CURL_EXIT; \
	fi; \
	if ! printf '%s' "$$HTTP_CODE" | grep -q '^2'; then \
	  kill $$MOONLIGHT_PID >/dev/null 2>&1 || true; \
	  wait $$MOONLIGHT_PID >/dev/null 2>&1 || true; \
	  echo "Sunshine pairing API returned HTTP $$HTTP_CODE."; \
	  if [ -f $$PAIR_RESPONSE_FILE ]; then cat $$PAIR_RESPONSE_FILE; fi; \
	  exit 1; \
	fi; \
	printf '%s\n' "Sunshine pairing API accepted the PIN. Waiting for Moonlight to finish..."; \
	wait $$MOONLIGHT_PID

plan: ## Plan profile changes (terraform or vagrant)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-resolve --profile $(PROFILE) --validate
	@./scripts/tf-plan $(PROFILE)

profiles.list: ## List available profiles with details
	@./scripts/profiles-list --with-details

profiles.menu: ## Interactive profile selector
	@./scripts/profile-menu

providers.status: ## Check provider configuration and connectivity
	@mkdir -p ./tmp; \
	printf '%s\n' 'Provider           Configured  Reachable  Notes'; \
	printf '%s\n' '-----------------  ----------  ---------  -------------------------------------------'; \
	AWS_CONFIGURED=no; AWS_REACHABLE=no; AWS_NOTES='missing AWS_PROFILE/AWS credentials'; \
	if [ -n "$${AWS_PROFILE:-}" ] || [ -n "$${AWS_ACCESS_KEY_ID:-}" ]; then \
		AWS_CONFIGURED=yes; \
		if ! command -v aws >/dev/null 2>&1; then \
			AWS_NOTES='configured, but aws cli not found'; \
		elif aws sts get-caller-identity >/dev/null 2>&1; then \
			AWS_REACHABLE=yes; AWS_NOTES='aws sts ok'; \
		else \
			AWS_NOTES='configured, but aws sts failed - Please, run: make aws.login'; \
		fi; \
	fi; \
	printf '%-17s  %-10s  %-9s  %s\n' 'aws' "$$AWS_CONFIGURED" "$$AWS_REACHABLE" "$$AWS_NOTES"; \
	LOCAL_VBOX_CONFIGURED=no; LOCAL_VBOX_REACHABLE=no; LOCAL_VBOX_NOTES='vagrant/virtualbox not found'; \
	if command -v vagrant >/dev/null 2>&1 || command -v VBoxManage >/dev/null 2>&1; then \
		LOCAL_VBOX_CONFIGURED=yes; \
		if command -v VBoxManage >/dev/null 2>&1; then LOCAL_VBOX_REACHABLE=yes; LOCAL_VBOX_NOTES='VBoxManage available'; else LOCAL_VBOX_NOTES='vagrant present, VBoxManage missing'; fi; \
	fi; \
	printf '%-17s  %-10s  %-9s  %s\n' 'local-virtualbox' "$$LOCAL_VBOX_CONFIGURED" "$$LOCAL_VBOX_REACHABLE" "$$LOCAL_VBOX_NOTES"; \
	LOCAL_VMWARE_CONFIGURED=no; LOCAL_VMWARE_REACHABLE=no; LOCAL_VMWARE_NOTES='vagrant/vmrun not found'; \
	if command -v vagrant >/dev/null 2>&1 || command -v vmrun >/dev/null 2>&1; then \
		LOCAL_VMWARE_CONFIGURED=yes; \
		if command -v vmrun >/dev/null 2>&1; then LOCAL_VMWARE_REACHABLE=yes; LOCAL_VMWARE_NOTES='vmrun available'; else LOCAL_VMWARE_NOTES='vagrant present, vmrun missing'; fi; \
	fi; \
	printf '%-17s  %-10s  %-9s  %s\n' 'local-vmware' "$$LOCAL_VMWARE_CONFIGURED" "$$LOCAL_VMWARE_REACHABLE" "$$LOCAL_VMWARE_NOTES"; \
	TR_HOST="$${TRUENAS_HOST:-}"; TR_PORT="$${TRUENAS_SSH_PORT:-22}"; TR_USER="$${TRUENAS_SSH_USER:-terraform}"; \
	TR_CONFIGURED=no; TR_REACHABLE=no; TR_NOTES='missing TRUENAS_HOST'; \
	if [ -n "$$TR_HOST" ]; then \
		TR_CONFIGURED=yes; TR_NOTES="host=$$TR_HOST"; \
		if nc -z -w 2 $$TR_HOST $$TR_PORT >/dev/null 2>&1; then TR_REACHABLE=yes; TR_NOTES="ssh port $$TR_PORT reachable"; else TR_NOTES="ssh port $$TR_PORT unreachable"; fi; \
		if [ -n "$${TRUENAS_SSH_PRIVATE_KEY_FILE:-}" ] && [ -f "$${TRUENAS_SSH_PRIVATE_KEY_FILE}" ]; then \
			if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=./tmp/known_hosts -p $$TR_PORT -i "$${TRUENAS_SSH_PRIVATE_KEY_FILE}" $$TR_USER@$$TR_HOST 'midclt call system.version >/dev/null 2>&1 && echo ok' 2>/dev/null | grep -q ok; then \
				TR_REACHABLE=yes; TR_NOTES='ssh auth ok; midclt reachable'; \
			else \
				TR_NOTES='host reachable; ssh auth or permissions failed'; \
			fi; \
		fi; \
		if [ -n "$${TRUENAS_API_KEY:-}" ] && curl -ksS --connect-timeout 3 --max-time 8 -H "Authorization: Bearer $$TRUENAS_API_KEY" "https://$$TR_HOST/api/v2.0/system/version" >/dev/null 2>&1; then \
			TR_REACHABLE=yes; TR_NOTES='api key accepted'; \
		fi; \
	fi; \
	printf '%-17s  %-10s  %-9s  %s\n' 'truenas' "$$TR_CONFIGURED" "$$TR_REACHABLE" "$$TR_NOTES"; \
	VULTR_CONFIGURED=no; VULTR_REACHABLE=no; VULTR_NOTES='missing VULTR_API_KEY'; \
	if [ -n "$${VULTR_API_KEY:-}" ]; then \
		VULTR_CONFIGURED=yes; \
		if curl -fsS -H "Authorization: Bearer $$VULTR_API_KEY" https://api.vultr.com/v2/account >/dev/null 2>&1; then VULTR_REACHABLE=yes; VULTR_NOTES='api ok'; else VULTR_NOTES='configured, but api call failed'; fi; \
	fi; \
	printf '%-17s  %-10s  %-9s  %s\n' 'vultr' "$$VULTR_CONFIGURED" "$$VULTR_REACHABLE" "$$VULTR_NOTES"

provision: ## Upload and run OS-appropriate provisioning scripts on the instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-provision $(PROFILE)

provision.clear-state: ## Clear remote provisioning state, logs, and downloads
	@$(RESOLVE_WINDOWS_IP); \
	SSH_OPTS='-o StrictHostKeyChecking=no -o ServerAliveInterval=10 -o WarnWeakCrypto=no-pq-kex -i $(SSH_PUBLIC_KEY_FILE)'; \
	ssh $$SSH_OPTS Administrator@$$IP 'if (Test-Path "C:\Users\Administrator\provision\state") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\state" }; if (Test-Path "C:\Users\Administrator\provision\logs") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\logs" }; if (Test-Path "C:\Users\Administrator\provision\downloads") { Remove-Item -Recurse -Force "C:\Users\Administrator\provision\downloads" }'

provision.restart: provision.clear-state provision ## Clear remote state then re-provision

rdp: ## Write ./tmp/windows.rdp and open it (auto-pastes the password)
	@$(RESOLVE_WINDOWS_IP); \
	$(RESOLVE_WINDOWS_PASSWORD); \
	printf '%s\n' \
	  "full address:s:$$IP" \
	  "username:s:Administrator" \
	  "prompt for credentials on client:i:1" \
	  "administrative session:i:1" \
	  "screen mode id:i:2" \
	  "session bpp:i:32" \
	  "redirectclipboard:i:1" \
	  "audiomode:i:0" \
	  > ./tmp/windows.rdp; \
	printf '%s' "$$PW" | pbcopy; \
	open -a "Microsoft Remote Desktop" ./tmp/windows.rdp || open ./tmp/windows.rdp; \
	sleep 3; \
	osascript -e 'tell application "System Events" to keystroke "v" using command down' -e 'tell application "System Events" to key code 36'

reboot: ## Reboot the instance
	@$(RESOLVE_WINDOWS_IP); \
	SSH_OPTS='-o StrictHostKeyChecking=no -o ServerAliveInterval=10 -o WarnWeakCrypto=no-pq-kex -i $(SSH_PUBLIC_KEY_FILE)'; \
	ssh $$SSH_OPTS Administrator@$$IP 'shutdown /r /t 0'

show-password: ## Display the instance's default password
	@$(RESOLVE_WINDOWS_PASSWORD); \
	echo "$$PW"

ssh: ## SSH into the profile's instance
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-ssh $(PROFILE)

ssh.wait: ## Wait until SSH on the profile's instance accepts connections
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-ssh-wait $(PROFILE)

sunshine: ## Open the Sunshine web UI for the instance
	@$(RESOLVE_WINDOWS_IP); \
	open "https://$$IP:47990" || open -a "Google Chrome" "https://$$IP:47990"

sunshine.wait: ## Wait until the Sunshine API accepts authenticated requests
	@$(RESOLVE_WINDOWS_IP); \
	ATTEMPT=1; \
	MAX_ATTEMPTS=20; \
	printf '%s\n' "Waiting for Sunshine API on $$IP:47990..."; \
	while [ $$ATTEMPT -le $$MAX_ATTEMPTS ]; do \
		HTTP_CODE=$$(curl -sS -k \
		  -u "sunshine:$(EPHEMERAL_SUNSHINE_PASSWORD)" \
		  -o /dev/null \
		  -w "%{http_code}" \
		  "https://$$IP:47990/api/config"); \
		CURL_EXIT=$$?; \
		if [ $$CURL_EXIT -eq 0 ] && printf '%s' "$$HTTP_CODE" | grep -q '^2'; then \
			printf '%s\n' "Sunshine API is ready on $$IP:47990"; \
			exit 0; \
		fi; \
		printf '%s\n' "Sunshine API not ready yet (attempt $$ATTEMPT/$$MAX_ATTEMPTS, curl=$$CURL_EXIT, http=$$HTTP_CODE). Sleeping 2 seconds..."; \
		sleep 2; \
		ATTEMPT=$$((ATTEMPT + 1)); \
	done; \
	printf '%s\n' "Sunshine API did not become ready in time."; \
	exit 1

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

upload: ## scp ./upload/* to the instance (skips files that already exist remotely)
	@$(RESOLVE_WINDOWS_IP); \
	SSH_OPTS='-o StrictHostKeyChecking=no -o ServerAliveInterval=10 -o WarnWeakCrypto=no-pq-kex -i $(SSH_PUBLIC_KEY_FILE)'; \
	REMOTE_UPLOAD_DIR='C:\Users\Administrator\upload'; \
	REMOTE_DESKTOP_DIR='C:\Users\Administrator\Desktop\upload'; \
	printf '%s\n' "Preparing remote upload folder on $$IP..."; \
	ssh $$SSH_OPTS Administrator@$$IP "New-Item -ItemType Directory -Force '$$REMOTE_UPLOAD_DIR' | Out-Null; if (!(Test-Path '$$REMOTE_DESKTOP_DIR')) { cmd /c mklink /J \"$$REMOTE_DESKTOP_DIR\" \"$$REMOTE_UPLOAD_DIR\" >nul 2>&1 }"; \
	if [ ! -d ./upload ]; then \
		printf '%s\n' "No ./upload directory found. Skipping upload."; \
		exit 0; \
	fi; \
	find ./upload -type f ! -name '.gitkeep' -exec sh -c '\
		FILE="$$1"; \
		REL_PATH="$${FILE#./upload/}"; \
		REL_PATH_WIN=$$(printf "%s" "$$REL_PATH" | sed "s#/#\\\\\\\\#g"); \
		REL_DIR=$$(dirname "$$REL_PATH"); \
		if [ "$$REL_DIR" = "." ]; then \
			REMOTE_DIR="C:\\Users\\Administrator\\upload"; \
		else \
			REL_DIR_WIN=$$(printf "%s" "$$REL_DIR" | sed "s#/#\\\\\\\\#g"); \
			REMOTE_DIR="C:\\Users\\Administrator\\upload\\$$REL_DIR_WIN"; \
		fi; \
		ssh '"$$SSH_OPTS"' Administrator@'"$$IP"' "New-Item -ItemType Directory -Force '\''$$REMOTE_DIR'\'' | Out-Null"; \
		if ssh '"$$SSH_OPTS"' Administrator@'"$$IP"' "if (Test-Path '\''C:\\Users\\Administrator\\upload\\$$REL_PATH_WIN'\'') { exit 0 } else { exit 1 }" >/dev/null 2>&1; then \
			printf "%s\n" "Skipping existing upload file: $$REL_PATH"; \
		else \
			printf "%s\n" "Uploading: $$REL_PATH"; \
			scp '"$$SSH_OPTS"' "$$FILE" Administrator@'"$$IP"':/C:/Users/Administrator/upload/"$$REL_PATH"; \
		fi \
	' sh {} \;

validate: ## Validate a profile from config/catalog.yaml
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@./scripts/profile-resolve --profile $(PROFILE) --validate

xpra: ## Launch a remote GUI app via Xpra (requires APP=<cmd>)
	@if [ -z "$(PROFILE)" ]; then exec ./scripts/profile-run $@; fi
	@if [ -z "$(APP)" ]; then echo "Usage: make xpra PROFILE=<name> APP=<command>"; exit 2; fi
	@./scripts/profile-xpra $(PROFILE) $(APP)
