# Build context: repository root (see deploy/docker-compose.yml)
FROM node:22-alpine AS build
WORKDIR /repo
COPY package.json package-lock.json* ./
COPY packages/widget-sdk/package.json packages/widget-sdk/
COPY apps/web/package.json apps/web/
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY packages/widget-sdk packages/widget-sdk
COPY apps/web apps/web
# Builds the widget into apps/web/public/sdk/v1, then the SPA (which copies public/ into dist/)
RUN npm run build

FROM caddy:2-alpine
COPY apps/web/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /repo/apps/web/dist /srv
EXPOSE 80
