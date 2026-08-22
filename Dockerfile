# runs lazycatter in a container so deps filesystem and process are boxed
# off from your host
# `docker compose down` is itself a hard kill
FROM python:3.12-slim

# no .pyc writes (plays nice with read_only)
# unbuffered logs so `docker compose logs -f` streams straight away
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY bot/requirements.txt ./bot/requirements.txt
RUN pip install --no-cache-dir -r bot/requirements.txt

COPY skill ./skill
COPY bot ./bot

# ui binds to 0.0.0.0 INSIDE the container
# compose maps it to your hosts 127.0.0.1 only
# no token is baked into the image
# the ui-gate secret comes from .env at runtime
# and the discord bot token is entered in the ui
EXPOSE 8787
ENV HOST=0.0.0.0
CMD ["python", "bot/app.py"]
