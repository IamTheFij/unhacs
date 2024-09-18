OPEN_CMD := $(shell type xdg-open &> /dev/null && echo 'xdg-open' || echo 'open')
NAME := unhacs
ENV := env

.PHONY: default
default: test

# Runs package
.PHONY: run
run:
	poetry run $(NAME) list

.PHONY: install
install:
	poetry install

.PHONY: devenv
devenv: install

.PHONY: lint
lint: devenv
	poetry run pre-commit run --all-files

# Runs tests
.PHONY: test
test: devenv
	poetry run python -m unittest discover tests

# Builds wheel for package to upload
.PHONY: build
build:
	poetry build

# Verify that the python version matches the git tag so we don't push bad shas
.PHONY: verify-tag-version
verify-tag-version:
	$(eval TAG_NAME = $(shell [ -n "$(DRONE_TAG)" ] && echo $(DRONE_TAG) || git describe --tags --exact-match))
	test "v$(shell poetry version | awk '{print $$2}')" = "$(TAG_NAME)"

# Upload to pypi
.PHONY: upload
upload: verify-tag-version build
	poetry publish

# Uses twine to upload to test pypi
.PHONY: upload-test
upload-test: verify-tag-version build
	poetry publish --repository testpypi

# Cleans all build, runtime, and test artifacts
.PHONY: clean
clean:
	rm -fr ./build *.egg-info ./htmlcov ./.coverage ./.pytest_cache ./.tox
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -delete

# Cleans dist and env
.PHONY: dist-clean
dist-clean: clean
	rm -fr ./dist

# Install pre-commit hooks
.PHONY: install-hooks
install-hooks: devenv
	poetry run pre-commit install -f --install-hooks

# Generates test coverage
.coverage: devenv
	poetry run pytest

# Builds coverage html
htmlcov/index.html: .coverage
	poetry run coverage html

# Opens coverage html in browser (on macOS and some Linux systems)
.PHONY: open-coverage
open-coverage: htmlcov/index.html
	$(OPEN_CMD) htmlcov/index.html

# Cleans out docs
.PHONY: docs-clean
docs-clean:
	rm -fr docs/build/* docs/source/code/*

# Builds docs
docs/build/html/index.html:
	@echo TODO: Make docs

# Shorthand for building docs
.PHONY: docs
docs: docs/build/html/index.html

.PHONY: clean-all
clean-all: clean dist-clean docs-clean
