FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    django==4.2.7 \
    djangorestframework==3.14.0 \
    mysqlclient==2.2.0 \
    redis==5.0.1 \
    python-dotenv==1.0.0 \
    requests==2.31.0

COPY ./oam/ /app/

EXPOSE 8081/tcp
CMD ["python", "/app/manage.py", "runserver", "0.0.0.0:8081"]
