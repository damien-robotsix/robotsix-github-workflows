.PHONY: test lint pytest shell-tests help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

test: pytest shell-tests  ## Run all tests (Python + shell)

pytest:  ## Run Python/pytest test suites
	pip install pytest --quiet
	pytest tests/test-pin-bump.py tests/test-lint-sarif-permissions.py -v

shell-tests:  ## Run shell test scripts
	bash tests/test-apply-branch-protection.sh
	bash tests/test-config-ownership-check.sh
	bash tests/test-baseline-check.sh

lint:  ## Run pre-commit hooks (actionlint, yamllint, shellcheck)
	pre-commit run --all-files
