FROM registry.cern.ch/docker.io/library/node:24-slim AS builder

WORKDIR /src
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# ponytail: build-only skips type-check; CI runs vue-tsc separately
RUN npm run build-only

FROM registry.cern.ch/docker.io/nginxinc/nginx-unprivileged:1.29-alpine

COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /src/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
