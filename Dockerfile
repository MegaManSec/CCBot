FROM python:3.13-alpine

WORKDIR /src

COPY setup.py MANIFEST.in README.md LICENSE ./
COPY ccbot/ ./ccbot/

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

CMD ["ccbot"]
