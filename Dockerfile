# Imagen de Cloudin: Django + gunicorn. La usan Render (render.yaml, plan gratis:
# DESPLIEGUE-GRATIS.md) y Cloudflare Containers (wrangler.jsonc: DESPLIEGUE-CLOUDFLARE.md),
# y sirve igual en cualquier servidor con Docker.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
    AWS_RESPONSE_CHECKSUM_VALIDATION=when_required

WORKDIR /app

# Primero las dependencias: si solo cambia el código, esta capa se reutiliza.
COPY requirements.txt requirements-produccion.txt ./
RUN pip install -r requirements-produccion.txt

COPY . .

# Estáticos comprimidos para WhiteNoise. Con DEBUG=0 settings.py exige llaves reales,
# pero collectstatic no las usa: valores de relleno solo para este paso.
RUN DEBUG=0 ALLOWED_HOSTS=localhost CREDENTIAL_KEY=relleno \
    SECRET_KEY=relleno-solo-para-collectstatic-0000000000000000000000000000 \
    python manage.py collectstatic --noinput --verbosity 0

RUN useradd --create-home cloudin && chown -R cloudin /app
USER cloudin

EXPOSE 8000

# Al arrancar: migraciones (control y restaurantes) y superusuario inicial; luego
# gunicorn. Un proceso con hilos: la caché de Django vive en su memoria y debe ser una.
# El puerto: el que diga PORT (Render pone 10000) o 8000 (Cloudflare no lo define).
CMD ["sh", "-c", "python manage.py preparar_servidor && exec gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 120 --forwarded-allow-ips='*' --access-logfile - --error-logfile -"]
