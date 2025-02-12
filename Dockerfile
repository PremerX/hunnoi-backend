# Stage 1: Build Stage
FROM python:3.12-slim AS build
WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /code/requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /code/requirements.txt

# Stage 2: Production Runtime Stage
FROM python:3.12-slim AS runtime
WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 \
    && wget -O /etc/apt/trusted.gpg.d/deb-multimedia-keyring.gpg https://www.deb-multimedia.org/pool/main/d/deb-multimedia-keyring/deb-multimedia-keyring_2023.03.30_all.deb \
    && echo "deb http://www.deb-multimedia.org bookworm main non-free" | tee /etc/apt/sources.list.d/multimedia.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

COPY ./app /code/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]