set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load

registry := "ghcr.io"
image := registry + "/suraj-ram/pagehost"
source := "https://github.com/Suraj-Ram/pagehost"
revision := `git rev-parse HEAD`

# List the CI commands.
default:
    @just --list

# Run the unit and acceptance tests across the available cores.
test-unit:
    uv run --python 3.12 --frozen --extra dev pytest -n auto tests

# Run the end-to-end scenarios across the available cores.
test-e2e:
    uv run --python 3.12 --frozen --extra dev pytest -n auto pagehost-build-kit/tests/e2e

# Run the unit tests and the end-to-end scenarios at the same time.
[parallel]
test: test-unit test-e2e

# Build the app image. This step runs on main.
build-image:
    #!/usr/bin/env bash
    set -euo pipefail
    branch="$(git rev-parse --abbrev-ref HEAD)"
    if [ "$branch" != "main" ]; then
        echo "Image builds run on main." >&2
        exit 1
    fi
    DOCKER_BUILDKIT=1 docker build \
        --label org.opencontainers.image.source={{ source }} \
        --tag {{ image }}:{{ revision }} \
        --tag {{ image }}:latest \
        .

# Publish the app image to the GitHub Container Registry.
publish-image: build-image
    #!/usr/bin/env bash
    set -euo pipefail
    user="$(GH_TOKEN="$GH_PACKAGES_PAT" gh api user --jq .login)"
    printf '%s' "$GH_PACKAGES_PAT" | docker login {{ registry }} --username "$user" --password-stdin
    docker push {{ image }}:{{ revision }}
    docker push {{ image }}:latest

# Run the full CI. On main, publish the image after the tests pass.
ci: test
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "$(git rev-parse --abbrev-ref HEAD)" = "main" ]; then
        just publish-image
    fi
