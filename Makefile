PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
CODEX_SKILLS_DIR ?= $(HOME)/.codex/skills
SKILL_NAME ?= linkedin-career-mcp
SKILL_SRC := $(CURDIR)/skills/$(SKILL_NAME)
SKILL_LINK := $(CODEX_SKILLS_DIR)/$(SKILL_NAME)
OLLAMA_MODEL ?= qwen3:4b
OLLAMA_INSTALL_URL ?= https://ollama.com/install.sh

.PHONY: install install-python install-ollama ollama-model venv skill-link match-jobs launch-website test lint clean

install: install-python install-ollama ollama-model skill-link

install-python: venv

venv: $(VENV)/.installed

$(VENV)/.installed: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e ".[dev]"
	touch $(VENV)/.installed

skill-link:
	@test -f "$(SKILL_SRC)/SKILL.md" || (echo "Missing $(SKILL_SRC)/SKILL.md" && exit 1)
	mkdir -p "$(CODEX_SKILLS_DIR)"
	@if [ -L "$(SKILL_LINK)" ]; then \
		current_target=$$(readlink "$(SKILL_LINK)"); \
		if [ "$$current_target" != "$(SKILL_SRC)" ]; then \
			ln -sfn "$(SKILL_SRC)" "$(SKILL_LINK)"; \
		fi; \
	elif [ -e "$(SKILL_LINK)" ]; then \
		echo "$(SKILL_LINK) exists and is not a symlink"; \
		exit 1; \
	else \
		ln -s "$(SKILL_SRC)" "$(SKILL_LINK)"; \
	fi

install-ollama:
	@if command -v ollama >/dev/null 2>&1; then \
		echo "Ollama already installed: $$(command -v ollama)"; \
	else \
		curl -fsSL "$(OLLAMA_INSTALL_URL)" | sh; \
	fi

ollama-model:
	ollama pull "$(OLLAMA_MODEL)"

match-jobs: venv
	$(VENV)/bin/linkedin-career-match-jobs

launch-website: venv
	$(VENV)/bin/linkedin-career-webapp

test: venv
	$(VENV_PYTHON) -m pytest

lint: venv
	$(VENV_PYTHON) -m ruff check .

clean:
	rm -rf $(VENV)
