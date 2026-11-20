FROM python:3.11-slim

WORKDIR /app

COPY ./ocs/src/ /app/src/

EXPOSE 3869/tcp
EXPOSE 3869/sctp
CMD ["python", "/app/src/ocs_client.py"]