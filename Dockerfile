# syntax=docker/dockerfile:1
FROM python:3.15-slim AS build
WORKDIR /src
RUN pip install --no-cache-dir --disable-pip-version-check build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

FROM python:3.15-slim
LABEL org.opencontainers.image.title="flakewatch" \
      org.opencontainers.image.description="Flaky-test detection and root-cause classification from JUnit XML" \
      org.opencontainers.image.source="https://github.com/baggy2797/flakewatch" \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 flake \
    && mkdir -p /work/.flakewatch \
    && chown -R flake:flake /work
COPY --from=build /dist/*.whl /tmp/
RUN pip install --disable-pip-version-check /tmp/*.whl && rm -f /tmp/*.whl
USER flake
WORKDIR /work
ENTRYPOINT ["flakewatch"]
CMD ["--help"]
