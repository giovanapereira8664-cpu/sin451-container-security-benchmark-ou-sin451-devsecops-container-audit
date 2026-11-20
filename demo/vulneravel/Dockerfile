FROM python:alpine
RUN apk add --no-cache curl
ENV DB_PASSWORD=abc123
COPY app.py /app/app.py
USER root
CMD ["python", "/app/app.py"]
