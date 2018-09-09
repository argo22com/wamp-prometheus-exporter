FROM python:3.7-alpine
ADD requirements.txt ./
RUN apk add --no-cache --virtual=build-dependencies g++ && \
 pip install --no-cache-dir -r requirements.txt && \
 apk del --purge \
    build-dependencies && \
 rm -rf \
    /root/.cache \
    /tmp/*

EXPOSE 9123
ENV PYTHONUNBUFFERED=1
COPY exporter.py ./
CMD ["python", "exporter.py"]
