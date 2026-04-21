# Contributing to wagtail-pdf-converter

Thank you for your interest in contributing!

## Getting Started

Requirements

- A Python 3.10+ virtual environment.
- Docker & Docker Compose (for Postgres).

1.  Install dependencies in your virtual environment:
    ```bash
    python -m pip install -e ".[dev]"
    pre-commit install
    ```
2.  Start the postgres container:

    ```bash
    docker compose up -d

    # or use `inv up`
    ```

3.  Verify setup by running tests to ensure everything is working correctly:
    ```bash
    pytest
    ```

## Development Workflow

### Code Style & Quality

We use `ruff` for linting and formatting python code.

```bash
inv lint        # Check for lint issues
inv lint --fix  # Auto-fix lint issues
ruff format .   # Format code
```

## Documentation

Documentation is built with `zensical`. To build and preview the docs:

```bash
zensical build --clean
zensical serve
```

Always update the docs when adding new features or changing existing behavior. [Here](https://google.github.io/styleguide/docguide/best_practices.html) are some good guidelines to follow when writing docs.

## Submitting a Pull Request

1.  Keep PRs small and focused on a single change.
2.  Ensure all tests pass and coverage is maintained.
3.  Provide a clear description of the change and link to any relevant issues.
4.  Update `CHANGELOG.md` to reflect the changes, under the `Unreleased` section.
