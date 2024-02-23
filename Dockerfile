FROM python:3.11

# Install OpenSSL
RUN apt-get update && apt-get install -y openssl


RUN mkdir /app
COPY /web /app
# Generate SSL certificate and private key into the certs folder
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /app/server.key -out /app/server.crt \
    -subj "/C=US/ST=California/L=San Francisco/O=MyOrg/OU=MyUnit/CN=mydomain.com"
COPY pyproject.toml /app
COPY README.md /app
COPY requirements.txt /app
WORKDIR /app
ENV PYTHONPATH=${PYTHONPATH}:${PWD}

RUN pip3 install poetry
RUN pip3 install -r requirements.txt
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev

EXPOSE 80

ENTRYPOINT ["python","web.py"]
# ENTRYPOINT ["python","src/web.py"]