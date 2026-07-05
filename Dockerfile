FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY backend ./backend
RUN pip install --no-cache-dir -e .
COPY ui ./ui
COPY skills ./skills
COPY config ./config
COPY sample_data ./sample_data
COPY scripts ./scripts
EXPOSE 8600 8501
CMD ["uvicorn", "dsarp.api:app", "--host", "0.0.0.0", "--port", "8600"]
