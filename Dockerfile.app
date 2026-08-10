ARG RUNTIME_IMAGE=aihr-runtime:local
FROM ${RUNTIME_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/opt/aihr:/opt/aihr/src

USER root
WORKDIR /opt/aihr
COPY src ./src
COPY config ./config
COPY app ./app

EXPOSE 8501
CMD ["streamlit", "run", "app/Home.py", "--server.address=0.0.0.0", "--server.port=8501"]

