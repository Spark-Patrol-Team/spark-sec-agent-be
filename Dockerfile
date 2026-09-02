FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY src ./src

RUN pip install --no-cache-dir --timeout 120 -i https://mirrors.cloud.tencent.com/pypi/simple .

EXPOSE 8080

CMD ["uvicorn", "sec_agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
