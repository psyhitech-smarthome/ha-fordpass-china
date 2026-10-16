FROM python:3.13-slim-bookworm

RUN apt-get update -qq && apt-get install -y --no-install-recommends gcc libc6-dev patchelf
COPY liblog_stub.c /tmp/liblog_stub.c
RUN gcc -shared -fPIC -o /usr/local/lib/liblog.so /tmp/liblog_stub.c
COPY server.py /app/server.py

ENV LD_LIBRARY_PATH=/usr/local/lib
CMD ["python", "/app/server.py"]
