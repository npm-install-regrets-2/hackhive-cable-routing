FROM node:22-alpine AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY cable_planner ./cable_planner
COPY shared/schema ./shared/schema
COPY examples/inputs ./examples/inputs
COPY --from=frontend /web/dist ./frontend/dist
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "cable_planner.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
