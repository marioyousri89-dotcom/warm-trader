FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir anthropic websocket-client
COPY *.py ./
ENV PYTHONUNBUFFERED=1
# Secrets go in your host's environment settings, NEVER in this file:
#   ANTHROPIC_API_KEY, DASHBOARD_TOKEN (required), ETORO_API_KEY + ETORO_USER_KEY (DEMO keys), MIRROR_TO_BROKERS=1 (optional)
# Mount a volume at /data so the agents' knowledge survives restarts.
RUN mkdir -p /data
# --live tries OKX, Bybit, Coinbase, Kraken, then Binance; if all refuse, the app falls back to the simulator by itself.
CMD python main.py --host 0.0.0.0 --port $PORT --db /data/brain.db --keep --live --academy
