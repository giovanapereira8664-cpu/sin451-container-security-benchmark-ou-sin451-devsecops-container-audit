FROM python:3.12-alpine3.20
RUN adduser -D -u 10001 app
COPY app.py /app/app.py
USER app
CMD ["python", "/app/app.py"]
