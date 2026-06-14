PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
CODEX_SKILLS_DIR ?= $(HOME)/.codex/skills
SKILL_NAME ?=
SKILL_NAMES ?= $(if $(SKILL_NAME),$(SKILL_NAME),linkedin-career-mcp master-resume-yaml)
OLLAMA_MODEL ?= qwen3:4b
OLLAMA_INSTALL_URL ?= https://ollama.com/install.sh
WEBSITE_HOST ?= 127.0.0.1
WEBSITE_PORT ?= 8765
JOB_IDS ?= all
LINKEDIN_DELAY_SECONDS ?= 2
ARTIFACT_MODE ?= resumes-only
DATE_POSTED ?= past_week
LIMIT_PER_QUERY ?= 10
MAX_QUERIES ?= 6
MAX_JOBS ?= 10

.PHONY: install install-python install-browser install-ollama ollama-model venv skill-link match-jobs regenerate-resumes first-draft-resumes refresh-static-artifacts launch-website stop-website restart-website test lint clean

install: install-python install-ollama ollama-model skill-link

install-python: venv install-browser

install-browser: venv
	$(VENV_PYTHON) -m playwright install chromium

venv: $(VENV)/.installed

$(VENV)/.installed: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e ".[dev,browser]"
	touch $(VENV)/.installed

skill-link:
	mkdir -p "$(CODEX_SKILLS_DIR)"
	@for skill_name in $(SKILL_NAMES); do \
		skill_src="$(CURDIR)/skills/$$skill_name"; \
		skill_link="$(CODEX_SKILLS_DIR)/$$skill_name"; \
		test -f "$$skill_src/SKILL.md" || (echo "Missing $$skill_src/SKILL.md" && exit 1); \
		if [ -L "$$skill_link" ]; then \
			current_target=$$(readlink "$$skill_link"); \
			if [ "$$current_target" != "$$skill_src" ]; then \
				ln -sfn "$$skill_src" "$$skill_link"; \
			fi; \
		elif [ -e "$$skill_link" ]; then \
			echo "$$skill_link exists and is not a symlink"; \
			exit 1; \
		else \
			ln -s "$$skill_src" "$$skill_link"; \
		fi; \
	done

install-ollama:
	@if command -v ollama >/dev/null 2>&1; then \
		echo "Ollama already installed: $$(command -v ollama)"; \
	else \
		curl -fsSL "$(OLLAMA_INSTALL_URL)" | sh; \
	fi

ollama-model:
	ollama pull "$(OLLAMA_MODEL)"

match-jobs: venv
	$(VENV)/bin/linkedin-career-match-jobs $(ARTIFACT_MODE) --date-posted "$(DATE_POSTED)" --limit-per-query "$(LIMIT_PER_QUERY)" --max-queries "$(MAX_QUERIES)" --max-jobs "$(MAX_JOBS)"

regenerate-resumes: venv
	$(VENV)/bin/linkedin-career-regenerate-resumes $(JOB_IDS) --linkedin-delay-seconds "$(LINKEDIN_DELAY_SECONDS)"

first-draft-resumes: venv
	@job_args=""; \
	if [ "$(JOB_IDS)" != "all" ]; then \
		for job_id in $(JOB_IDS); do \
			job_args="$$job_args --job-id $$job_id"; \
		done; \
	fi; \
	force_arg=""; \
	if [ "$(FIRST_DRAFT_FORCE)" = "1" ] || [ "$(FIRST_DRAFT_FORCE)" = "true" ]; then \
		force_arg="--force"; \
	fi; \
	$(VENV_PYTHON) scripts/application_resume_backport_first_drafts.py $$job_args $$force_arg

refresh-static-artifacts: venv
	$(VENV)/bin/linkedin-career-refresh-static-artifacts $(JOB_IDS)

launch-website: venv
	$(VENV)/bin/linkedin-career-webapp --host "$(WEBSITE_HOST)" --port "$(WEBSITE_PORT)" --open-browser

stop-website:
	@pids="$$(lsof -tiTCP:$(WEBSITE_PORT) -sTCP:LISTEN 2>/dev/null || true)"; \
	if [ -n "$$pids" ]; then \
		echo "Stopping website process(es) on port $(WEBSITE_PORT): $$pids"; \
		kill $$pids; \
	else \
		echo "No website process listening on port $(WEBSITE_PORT)"; \
	fi

restart-website: stop-website
	@sleep 1
	$(MAKE) launch-website

test: venv
	$(VENV_PYTHON) -m pytest

lint: venv
	$(VENV_PYTHON) -m ruff check .

clean:
	rm -rf $(VENV)
