FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn
COPY app.py .
COPY templates/ ./templates/
RUN mkdir -p /app/data
EXPOSE 9119
CMD ["gunicorn","-w","1","-b","0.0.0.0:9119","--timeout","120","--access-logfile","-","--error-logfile","-","app:app"]
