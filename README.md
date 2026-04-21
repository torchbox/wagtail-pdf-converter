# wagtail-pdf-converter

> PDF to Markdown conversion for Wagtail, powered by AI

[![PyPI](https://img.shields.io/pypi/v/wagtail-pdf-converter.svg)](https://pypi.org/project/wagtail-pdf-converter/)

[![Build status](https://github.com/torchbox/wagtail-pdf-converter/workflows/CI/badge.svg)](https://github.com/torchbox/wagtail-pdf-converter/actions)

[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-76877c?&logo=pre-commit&labelColor=1f2d23)](https://pre-commit.com/)

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

**Contents** _generated with [DocToc](https://github.com/thlorenz/doctoc)_

- [Supported versions](#supported-versions)
- [Development](#development)
    - [Requirements](#requirements)
        - [Core](#core)
        - [Extra](#extra)
    - [Getting Started](#getting-started)
    - [Running tests](#running-tests)
    - [pre-commit](#pre-commit)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Supported versions

- Python 3.10 - 3.14
- Django: 4.2, 5.1, 5.2, 6.0
- Wagtail: 6.3, 7.0, 7.1, 7.2

## Development

### Requirements

#### Core

- Python 3.10+

#### Extra

- Docker and Docker Compose, if you want to quickly set up a Postgres DB to work with

### Getting Started

1. With your preferred virtualenv activated, install the dependencies

```sh
python -m pip install --upgrade pip
python -m pip install -e ".[testing,ci,docs]"
```

You can also use [flit](https://flit.pypa.io/en/stable/):

```sh
python -m pip install flit
flit install
```

2. If you're using Postgres:

Spin up the postgres container:

```sh
inv up
```

Copy `.env.example` to `.env`:

```sh
cp -v .env.example .env
```

The `DATABASE_URL` in `.env` will be automatically picked up by the test settings. If no `.env` file exists, the project will use SQLite by default.

And you should be good to go

### Running tests

The simplest is to just run `pytest`.

If you wanna run the full tox suite, then run `tox` (You need to ensure you have all the different versions of python on your system, and [`tox` should know about them](https://stackoverflow.com/questions/75715657/getting-tox-to-use-the-python-version-set-by-pyenv)). You can speed things up by running all envs in parallel, via `tox -p auto`.

or, you can run them for a specific environment `tox -e python3.14-django5.2-wagtail7.2` or specific test
`tox -e python3.14-django5.2-wagtail7.2-sqlite wagtail_pdf_converter.tests.test_file.TestClass.test_method`

To run the test app interactively, use `tox -e interactive`, visit `http://127.0.0.1:8020/admin/` and log in with `admin`/`changeme`.

### pre-commit

Note that this project uses [pre-commit](https://github.com/pre-commit/pre-commit).
It is included in the project testing requirements. To set up locally, run the following in project root:

```shell
# initialize pre-commit
pre-commit install

# Optional, run all checks once for this, then the checks will run only on the changed files
git ls-files --others --cached --exclude-standard | xargs pre-commit run --files
```
