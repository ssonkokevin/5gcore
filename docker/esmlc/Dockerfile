FROM python:3.11-slim

WORKDIR /app

# pycrate provides the pycrate_asn1rt runtime the generated LCS-AP codec
# imports. The codec itself is committed under lib/codecs/.
RUN pip install --no-cache-dir pycrate==0.8.1

COPY ./corelib/ /app/corelib/
COPY ./lib/ /app/lib/
COPY ./esmlc/src/ /app/esmlc/src/
COPY ./esmlc/config/ /app/esmlc/config/

EXPOSE 9082/tcp
CMD ["python", "/app/esmlc/src/esmlc_sim.py"]
