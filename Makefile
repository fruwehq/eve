# Convenience wrapper only. The make layer was removed — use the `eve` CLI
# (or ./bin/eve) for everything. This Makefile exists solely to offer a familiar
# `make install` for putting the launcher on your PATH.
.DEFAULT_GOAL := help
.PHONY: install help

install: ## Install the eve launcher into ~/.local/bin
	@./scripts/install-cli

help: ## Show available targets
	@echo "Targets:"
	@echo "  make install   Install the eve launcher into ~/.local/bin"
	@echo
	@echo "Everything else is the eve CLI:  eve --help   (or ./bin/eve --help)"
