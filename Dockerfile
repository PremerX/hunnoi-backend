# Stage 1: Build Stage
FROM python:3.12-slim AS build

# ตั้งค่าโฟลเดอร์ทำงาน
WORKDIR /code

# ติดตั้ง dependencies ที่จำเป็นสำหรับการ build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# คัดลอก requirements.txt และติดตั้ง dependencies
COPY ./requirements.txt /code/requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /code/requirements.txt

# Stage 2: Production Runtime Stage
FROM python:3.12-slim AS runtime

# ตั้งค่าโฟลเดอร์ทำงาน
WORKDIR /code

# ติดตั้ง FFmpeg และ runtime dependencies ที่จำเป็น
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    iputils-ping \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# คัดลอก dependencies ที่ติดตั้งจาก Build Stage
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# คัดลอกโค้ดโปรเจกต์
COPY ./app /code/app

# เปิดพอร์ต 8000 สำหรับ FastAPI
EXPOSE 8000

# ใช้ Uvicorn สำหรับ production
CMD ["uvicorn", "app.test:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]