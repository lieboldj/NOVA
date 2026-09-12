FROM node:24-slim AS frontend
WORKDIR /ui
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js logo.png ./
COPY src ./src
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
COPY nova ./nova
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY migrations ./migrations
COPY Data_Collection.csv ./
COPY --from=frontend /ui/dist ./dist
RUN useradd --create-home --uid 10001 nova && mkdir -p /app/.data/documents && chown -R nova:nova /app
USER nova
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "nova.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
