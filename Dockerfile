FROM python:3.13-alpine
WORKDIR /usr/src/bot
RUN apk add --no-cache curl
COPY requirements.txt ./
RUN apk upgrade --no-cache \
    && pip install --no-cache-dir -r requirements.txt
