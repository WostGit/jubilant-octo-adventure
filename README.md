# ExploitGym GitHub Actions memory smoke test

This repository contains CI scaffolding for five ExploitGym task containers. **Task Dockerfiles/images are not included**; provide them under `tasks/<task>/Dockerfile` or adapt the workflow to pull published images before running.

The workflow measures container peak memory when cgroup v2 accounting is accessible, records exit/OOM/timeout data, and uploads per-task JSON artifacts. Successful container execution does not imply exploit success.

See `.github/workflows/container-memory-smoke.yml` and `scripts/container_memory_smoke.py`.

**Safety:** Use only reviewed images; kernel exploitation tasks generally require a dedicated isolated VM and are not expected to work in a normal unprivileged Docker container.
