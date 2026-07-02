PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
CODEX_SKILLS_DIR ?= $(HOME)/.codex/skills
SKILL_NAME ?=
SKILL_NAMES ?= $(if $(SKILL_NAME),$(SKILL_NAME),linkedin-career-mcp master-resume-yaml manual-resume-passthrough)
OLLAMA_MODEL ?= qwen3:4b
OLLAMA_INSTALL_URL ?= https://ollama.com/install.sh
WEBSITE_HOST ?= 127.0.0.1
WEBSITE_PORT ?= 8765
JOB_IDS ?= all
DATE_POSTED ?= past_week
LIMIT_PER_QUERY ?= 10
MAX_QUERIES ?= 6
MAX_JOBS ?= 10
MASTER_RESUME ?= profile/MASTER-RESUME.yml
JOD_MODEL ?= z-ai/glm-5.2
CORE_SKILL_MODEL ?= $(JOD_MODEL)
SECOND_PASS_MODEL ?= z-ai/glm-5.2
SECOND_PASS_TIMEOUT_SECONDS ?= 300
CODEX_COMMAND ?= codex
CODEX_MODEL ?= gpt-5.5
CODEX_TIMEOUT_SECONDS ?= 900
MANUAL_PASS_MASTER_RESUME_TEXT ?= profile/MP-MASTER-RESUME.txt
HIGHLIGHT_EXPERIENCE_COMPANY ?=
HIGHLIGHT_EXPERIENCE_JOB_ORDER ?=

.PHONY: install install-python install-browser install-ollama ollama-model venv skill-link seed-jobs regenerate-resumes regenerate-draft-resumes regenerate-resume-variants regenerate-aro-objects sync-draft-to-aro refine-draft-resumes highlight-draft-resumes manual-pass-resumes launch-website stop-website restart-website test lint clean

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

seed-jobs: venv
	$(VENV)/bin/linkedin-career-seed-jobs --date-posted "$(DATE_POSTED)" --limit-per-query "$(LIMIT_PER_QUERY)" --max-queries "$(MAX_QUERIES)" --max-jobs "$(MAX_JOBS)"

regenerate-draft-resumes: venv
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
	$(VENV_PYTHON) scripts/application_resume_generate_drafts.py --master-resume "$(MASTER_RESUME)" --api-model "$(CORE_SKILL_MODEL)" --jod-model "$(JOD_MODEL)" $$job_args $$force_arg

regenerate-resumes: regenerate-draft-resumes refine-draft-resumes

regenerate-resume-variants: regenerate-resumes

regenerate-aro-objects: venv
	@job_args=""; \
	if [ "$(JOB_IDS)" != "all" ]; then \
		for job_id in $(JOB_IDS); do \
			job_args="$$job_args --job-id $$job_id"; \
		done; \
	fi; \
	$(VENV_PYTHON) scripts/application_resume_regenerate_aros.py --master-resume "$(MASTER_RESUME)" $$job_args

sync-draft-to-aro: venv
	@job_args=""; \
	if [ "$(JOB_IDS)" != "all" ]; then \
		for job_id in $(JOB_IDS); do \
			job_args="$$job_args --job-id $$job_id"; \
		done; \
	fi; \
	$(VENV_PYTHON) scripts/application_resume_sync_drafts_to_aro.py $$job_args

refine-draft-resumes: venv
	@job_args=""; \
	if [ "$(JOB_IDS)" = "all" ]; then \
		job_args="--all-active"; \
	else \
		for job_id in $(JOB_IDS); do \
			job_args="$$job_args --job-id $$job_id"; \
		done; \
	fi; \
	$(VENV)/bin/linkedin-career-refine-resume $$job_args --master-resume "$(MASTER_RESUME)" --api-model "$(SECOND_PASS_MODEL)" --api-timeout-seconds "$(SECOND_PASS_TIMEOUT_SECONDS)"

highlight-draft-resumes: venv
	@job_args=""; \
	if [ "$(JOB_IDS)" != "all" ]; then \
		for job_id in $(JOB_IDS); do \
			job_args="$$job_args --job-id $$job_id"; \
		done; \
	fi; \
	filter_args=""; \
	if [ -n "$(HIGHLIGHT_EXPERIENCE_COMPANY)" ]; then \
		filter_args="$$filter_args --experience-company $(HIGHLIGHT_EXPERIENCE_COMPANY)"; \
	fi; \
	if [ -n "$(HIGHLIGHT_EXPERIENCE_JOB_ORDER)" ]; then \
		filter_args="$$filter_args --experience-job-order $(HIGHLIGHT_EXPERIENCE_JOB_ORDER)"; \
	fi; \
	$(VENV_PYTHON) scripts/application_resume_highlight_drafts.py --codex-command "$(CODEX_COMMAND)" --codex-model "$(CODEX_MODEL)" --timeout-seconds "$(CODEX_TIMEOUT_SECONDS)" $$job_args $$filter_args

manual-pass-resumes: venv
	@if [ "$(JOB_IDS)" = "all" ]; then \
		echo "Set JOB_IDS=<job_id ...> for manual-pass-resumes"; \
		exit 2; \
	fi; \
	job_args=""; \
	for job_id in $(JOB_IDS); do \
		job_args="$$job_args --job-id $$job_id"; \
	done; \
	$(VENV_PYTHON) scripts/application_resume_manual_pass.py --master-resume "$(MASTER_RESUME)" --master-resume-text "$(MANUAL_PASS_MASTER_RESUME_TEXT)" --codex-command "$(CODEX_COMMAND)" --codex-model "$(CODEX_MODEL)" --timeout-seconds "$(CODEX_TIMEOUT_SECONDS)" $$job_args

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
