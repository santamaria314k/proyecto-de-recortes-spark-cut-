FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Artefactos v6 de la RNN propia. Se incluyen en la imagen para que web y
# worker usen exactamente el mismo modelo en Docker y Kubernetes.
RUN test -f ml_artifacts/model_0.pt \
    && test -f ml_artifacts/tokenizer.model \
    && test -f ml_artifacts/context_ranker.joblib

# Los estáticos se sirven con WhiteNoise (sin nginx para /static).
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "sparkcut.wsgi:application", "--bind", "0.0.0.0:8000"]
