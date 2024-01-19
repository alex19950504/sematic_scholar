FROM python:3.11

RUN mkdir /app
COPY /web /app
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