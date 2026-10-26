# Stage 1: download the real dataset and train the model inside the build,
# so every image carries a model trained from a known commit.
FROM python:3.11-slim AS train
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
RUN PYTHONPATH=src python -m energy.train

# Stage 2: small runtime image, non-root user
FROM python:3.11-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY service/ service/
COPY --from=train /build/model/ model/
ENV PYTHONPATH=/app/src:/app PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
