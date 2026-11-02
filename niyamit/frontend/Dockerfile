# Niyamit Care Bridge: clinic dashboard and patient app (Next.js, standalone server).
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Where the Next.js server forwards /api/*. Rewrites are fixed at build time, so this is a build argument.
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -S niyamit && adduser -S niyamit -G niyamit
COPY --from=build --chown=niyamit:niyamit /app/.next/standalone ./
COPY --from=build --chown=niyamit:niyamit /app/.next/static ./.next/static
COPY --from=build --chown=niyamit:niyamit /app/public ./public
USER niyamit
EXPOSE 3000
CMD ["node", "server.js"]
