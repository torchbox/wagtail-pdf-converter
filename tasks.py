import shutil

from pathlib import Path

from invoke import task


# ============================================================================
# Docker compose utils
# ============================================================================


@task(help={"build": "Build images before starting containers."})
def up(c, build=False):
    """docker-compose up -d"""
    if build:
        c.run(
            "docker-compose up -d --build",
            pty=True,
        )
    else:
        c.run("docker-compose up -d", pty=True)


@task(help={"command": "Command to execute", "container": "Container name (default: db)"})
def exec(c, command, container="db"):
    """docker-compose exec [container] [command(s)]"""
    c.run(f"docker-compose exec {container} {command}", pty=True)


@task(help={"container": "Container name (default: db)", "follow": "Follow log output"})
def logs(c, container="db", follow=False):
    """docker-compose logs [container] [-f]"""
    if follow:
        c.run(f"docker-compose logs {container} -f", pty=True)
    else:
        c.run(f"docker-compose logs {container}", pty=True)


@task
def stop(c):
    """docker-compose stop"""
    c.run("docker-compose stop", pty=True)


@task(
    help={
        "volumes": "Remove named volumes declared in the `volumes` section of the Compose file and anonymous volumes attached to containers."
    }
)
def down(c, volumes=False):
    """docker-compose down"""
    if volumes:
        c.run("docker-compose down -v", pty=True)
    else:
        c.run("docker-compose down", pty=True)


# ============================================================================
# Cleanup utils
# ============================================================================


@task
def clean_pyc(c):
    """remove Python file artifacts"""

    patterns = ["*.pyc", "*.pyo", "__pycache__", "*.egg-info", ".ruff_cache"]

    for pattern in patterns:
        for path in Path(".").rglob(pattern):
            if path.is_file():
                path.unlink()
                print(f"Removed file: {path}")
            elif path.is_dir():
                shutil.rmtree(path)
                print(f"Removed directory: {path}")


@task
def clean_test(c):
    """remove test and coverage artifacts"""

    paths_to_remove = [
        ".tox/",
        ".coverage",
        "coverage.xml",
        "coverage.json",
        "htmlcov/",
        ".pytest_cache",
    ]

    for path_str in paths_to_remove:
        path = Path(path_str)
        if path.exists():
            if path.is_file():
                path.unlink()
                print(f"Removed file: {path}")
            elif path.is_dir():
                shutil.rmtree(path)
                print(f"Removed directory: {path}")


@task
def clean(c):
    """remove both Python file and test artifacts"""
    clean_pyc(c)
    clean_test(c)


# ============================================================================
# Linting & Formatting
# ============================================================================


@task(help={"fix": "let ruff lint & format your files"})
def lint(c, fix=False):
    """Run ruff"""
    if fix:
        c.run("ruff check --fix .", pty=True)
    else:
        c.run("ruff check .", pty=True)
