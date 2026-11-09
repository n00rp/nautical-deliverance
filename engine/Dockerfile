# syntax=docker/dockerfile:1
FROM python:3.14.10-slim-trixie@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966 AS build
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14.10-slim-trixie@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app/src PYTHONUNBUFFERED=1
# pip (with its vendored msgpack/urllib3/setuptools) is unused at runtime; drop it with its CVEs.
# R16: CVE-2026-109518 (apt < 3.0.4) is fixed in Debian but not yet in this base digest;
# remove this targeted upgrade once the python base image ships apt >= 3.0.4.
# zlib1g: CVE-2026-85091 / CVE-2026-76844 fixed in 1:1.3.dfsg+really1.3.1-1+deb13u1; same rule.
RUN apt-get update \
    && apt-get install -y --only-upgrade --no-install-recommends apt libapt-pkg7.0 zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home nd \
    && rm -rf /usr/local/lib/python3.14/site-packages/pip* /usr/local/lib/python3.14/ensurepip /usr/local/bin/pip*
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY src ./src
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["sh", "/usr/local/bin/docker-entrypoint.sh"]
