FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

# The repository keeps the canonical v7 source as a checksum-verified snapshot.
RUN python scripts/materialize_v7_source.py

# Runtime databases and secrets are provided at runtime; do not bake them into the image.
CMD ["python", "run.py"]
