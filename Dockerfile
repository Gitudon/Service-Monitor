FROM python:3.13.14-alpine3.24
WORKDIR /usr/src/bot
RUN apk add --no-cache curl
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
