FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Voix française Piper (synthèse vocale locale), téléchargée une fois au build
ARG PIPER_VOICE=fr_FR-siwis-medium
RUN python -m piper.download_voices ${PIPER_VOICE} --download-dir /app/voices
ENV PIPER_VOICE=${PIPER_VOICE}
COPY . .
RUN mkdir -p data/wiki
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
