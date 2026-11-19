FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/

EXPOSE 7777

ENV PCF_CONFIG=/app/config/pcf.yaml
ENV PCF_PCC_RULES=/app/config/pcc_rules.json
ENV PCF_SESSION_RULES=/app/config/session_rules.json
ENV PCF_QOS_PROFILES=/app/config/qos_profiles.json
ENV PCF_CHARGING_PROFILES=/app/config/charging_profiles.json
ENV PCF_TRAFFIC_CONTROL=/app/config/traffic_control_profiles.json
ENV PCF_USAGE_MONITORING=/app/config/usage_monitoring_profiles.json
ENV PCF_CONDITION_PROFILES=/app/config/condition_profiles.json
ENV PCF_PREDEFINED_RULES=/app/config/predefined_rules.json
ENV LOG_LEVEL=INFO

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:7777/health || exit 1

CMD ["python", "src/pcf_server.py"]