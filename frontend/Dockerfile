# Stage 1: Build
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# Stage 2: Serve
FROM nginx:1.27-alpine

RUN apk add --no-cache curl

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template

# Cloud Run uses PORT env var (default 8080)
# BACKEND_URL: Cloud Run backend service URL
ENV PORT=8080
ENV BACKEND_URL=http://backend:8080

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Restrict envsubst to only our variables (protect $host, $uri, $remote_addr etc.)
ENV NGINX_ENVSUBST_FILTER=^(PORT|BACKEND_URL)$

CMD ["nginx", "-g", "daemon off;"]
