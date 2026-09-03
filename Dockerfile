FROM python:3.10-slim

ENV ETESYNC_DATA_DIR "/data"
ENV ETESYNC_SERVER_HOSTS "0.0.0.0:37358,[::]:37358"

# Make this file a build dep for the next steps
COPY requirements.txt /app/
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.txt

COPY . /app
RUN pip install --no-cache-dir --no-deps /app

RUN set -ex ;\
        useradd etesync ;\
        mkdir -p /data ;\
        chown -R etesync: /data

VOLUME /data
EXPOSE 37358

USER etesync

ENTRYPOINT ["etesync-dav"]
