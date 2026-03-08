# Build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --legacy-peer-deps 2>/dev/null || npm install --legacy-peer-deps
COPY frontend/ ./
RUN npm run build

# Backend + serve frontend
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install backend deps
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/

# Copy built frontend into backend static
COPY --from=frontend-build /app/frontend/dist ./backend/static

EXPOSE 8000
# Default DATABASE_URL should be overridden by docker-compose to use postgres service
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
