# syntax=docker/dockerfile:1
# Build context: frontend/
FROM node:24.21.0-alpine AS build

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY packages ./packages
COPY apps/shop ./apps/shop
RUN pnpm install --frozen-lockfile --filter shop...

ARG VITE_API_URL=http://api.localhost
ENV VITE_API_URL=$VITE_API_URL
RUN pnpm --filter shop build

FROM nginx:1.30.5-alpine

COPY apps/shop/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/shop/dist /usr/share/nginx/html
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/run \
    && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid
USER nginx
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
