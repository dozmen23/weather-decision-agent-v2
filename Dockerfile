FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HISTORY_STORAGE_MODE=session

RUN useradd --create-home --uid 1000 appuser

WORKDIR /home/appuser/app

COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 7860

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=7860", "--server.headless=true"]
