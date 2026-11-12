import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def compose():
    return yaml.safe_load(read("docker-compose.yml"))


def runtime_stage(text):
    lines = text.splitlines()
    froms = [i for i, line in enumerate(lines) if line.upper().startswith("FROM ")]
    assert len(froms) == 2, "expected a build and a runtime stage"
    return "\n".join(lines[froms[1] :])


# Spec AC1: multi-stage uv build, the app extra, git/CA and an owned /data.
def test_image_builds_with_uv_and_installs_the_app_extra():
    text = read("Dockerfile")
    assert "python:3.13-slim" in text
    assert "ghcr.io/astral-sh/uv:0.8" in text
    assert "COPY --from=" in text and "/uv" in text
    for name in ("pyproject.toml", "uv.lock", "README.md", "src/"):
        assert name in text
    sync = next(line for line in text.splitlines() if "uv sync" in line)
    for flag in ("--frozen", "--no-dev", "--extra app", "--no-editable"):
        assert flag in sync


# Spec AC1: a non-root user with an owned writable /data and no bytecode.
def test_runtime_has_git_ca_a_non_root_user_and_owned_data():
    stage = runtime_stage(read("Dockerfile"))
    assert "git" in stage
    assert "ca-certificates" in stage
    assert "10001" in stage
    assert "USER tenon" in stage
    assert "/data" in stage and "chown" in stage
    assert "PYTHONDONTWRITEBYTECODE=1" in stage
    assert "/app/.venv/bin" in stage


# Spec AC1: the image runs the serve command and checks /health itself.
def test_image_starts_the_service_and_checks_health():
    text = read("Dockerfile")
    assert 'ENTRYPOINT ["tenon"]' in text
    cmd = next(line for line in text.splitlines() if line.startswith("CMD "))
    for part in ("provider", "serve", "/data/bundles", "/data/tenon.db", "0.0.0.0", "8080"):
        assert part in cmd
    assert "EXPOSE 8080" in text
    check = text[text.index("HEALTHCHECK") :]
    assert "urllib" in check and "/health" in check


# Spec AC1: no bearer token or other secret is baked into a layer.
def test_dockerfile_carries_no_secret():
    text = read("Dockerfile")
    assert "TENON_API_TOKEN" not in text
    assert not re.search(r"(?i)(api[_-]?token|webhook[_-]?secret|private[_-]?key)\s*=", text)


# Spec AC2: only Caddy is public; the service is reachable on the compose network.
def test_compose_runs_the_service_behind_caddy():
    stack = compose()
    services = stack["services"]
    assert set(services) == {"service", "caddy"}
    caddy = services["caddy"]
    assert caddy["image"] == "caddy:2"
    assert "80:80" in caddy["ports"]
    assert "443:443" in caddy["ports"]
    assert "443:443/udp" in caddy["ports"]
    assert any("Caddyfile" in mount for mount in caddy["volumes"])
    assert any(mount.startswith("caddy-data:") for mount in caddy["volumes"])
    assert any(mount.startswith("caddy-config:") for mount in caddy["volumes"])
    assert "TENON_DOMAIN" in caddy["environment"]
    assert "service" in caddy["depends_on"]
    assert caddy["restart"]


# Spec AC2: required token, optional webhook, a commit identity, read-only inputs.
def test_service_reads_its_config_and_mounts_inputs_read_only():
    service = compose()["services"]["service"]
    assert service["build"] == "."
    assert service["env_file"] == ".env"
    environment = service["environment"]
    assert ":?" in environment["TENON_API_TOKEN"]
    assert ":-" in environment["TENON_WEBHOOK_SECRET"]
    for key in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        assert environment[key]
    volumes = service["volumes"]
    assert "tenon-data:/data" in volumes
    assert "./bundles:/data/bundles:ro" in volumes
    assert "./secrets:/secrets:ro" in volumes
    assert "/tmp" in service["tmpfs"]


# Spec AC2: read-only root, no capabilities, a restart policy and a healthcheck.
def test_service_is_hardened_and_has_no_host_port():
    service = compose()["services"]["service"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["restart"] == "unless-stopped"
    assert "/health" in str(service["healthcheck"])
    assert service["expose"] == ["8080"]
    assert "ports" not in service


# Spec AC2: state lives in named volumes, not in the image or a bind mount.
def test_compose_declares_the_named_volumes():
    volumes = compose()["volumes"]
    assert set(volumes) == {"tenon-data", "caddy-data", "caddy-config"}


# Spec AC3: Caddy reads the domain, compresses and reverse-proxies the service.
def test_caddyfile_terminates_tls_and_proxies_the_service():
    text = read("Caddyfile")
    assert "{$TENON_DOMAIN:localhost}" in text
    assert "encode zstd gzip" in text
    assert "reverse_proxy service:8080" in text


# Spec AC1: local state, tests, docs and secrets never reach the build context.
def test_dockerignore_excludes_local_state():
    lines = {line.strip() for line in read(".dockerignore").splitlines() if line.strip()}
    for entry in (
        ".git",
        ".claude",
        ".venv",
        "tests",
        "docs",
        ".env*",
        "secrets",
        "bundles",
        "data",
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
    ):
        assert entry in lines


# Spec AC4: every operator input has a documented key and no real secret.
def test_env_example_lists_the_operator_keys():
    keys = {
        line.split("=", 1)[0]
        for line in read(".env.example").splitlines()
        if line.strip() and not line.startswith("#")
    }
    for key in (
        "TENON_API_TOKEN",
        "TENON_DOMAIN",
        "TENON_WEBHOOK_SECRET",
        "TENON_GITHUB_APP_ID",
        "TENON_GITHUB_APP_INSTALLATION_ID",
        "TENON_GITHUB_APP_PRIVATE_KEY",
        "TENON_GITHUB_API_URL",
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        assert key in keys
    assert "TENON_GITHUB_APP_PRIVATE_KEY=/secrets/app.pem" in read(".env.example")
    assert not re.search(r"(?m)=\s*[0-9a-f]{32,}\s*$", read(".env.example"))


# Spec AC4: the bundle/spec layout and the secret mount are prepared and ignored.
def test_bundle_and_secret_layout_is_ignored():
    assert "/data/bundles" in read("bundles/README.md")
    assert (ROOT / "secrets" / ".gitkeep").is_file()
    ignored = read(".gitignore")
    for entry in ("secrets/*", "!secrets/.gitkeep", "bundles/*", "!bundles/README.md", "data/"):
        assert entry in ignored
    assert "*.db" in ignored


# Spec AC4: the guide covers install, TLS, backups, rotation and the checklist.
def test_deployment_guide_covers_the_operations():
    text = read("docs/technical/DEPLOYMENT.md").lower()
    for part in (
        "prerequisite",
        "openssl rand -hex 32",
        "chmod 400",
        "docker compose up -d --build",
        "sqlite3",
        ".backup",
        "restore",
        "rotat",
        "upgrade",
        "docker compose logs",
        "security checklist",
        "internal ca",
        "443",
    ):
        assert part in text


# Spec AC4: operators can find the guide from the readme and the architecture.
def test_deployment_guide_is_linked():
    assert "DEPLOYMENT.md" in read("README.md")
    assert "DEPLOYMENT.md" in read("docs/technical/ARCHITECTURE.md")


# Spec AC5: every check above reads only static files, so the suite is offline.
