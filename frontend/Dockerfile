# syntax=docker/dockerfile:1
# =============================================================================
# SOT Analyzer - frontend
# =============================================================================

FROM node:22-alpine AS deps

WORKDIR /app

# Copy only the lockfile pair so dependency installation is cached independently
# of application source changes.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund


# --- Development -----------------------------------------------------------
FROM node:22-alpine AS development

WORKDIR /app
ENV NODE_ENV=development

COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]


# --- Build -----------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* values are inlined at build time, so the browser-facing API URL
# must be supplied here rather than only at runtime.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN npm run build


# --- Production ------------------------------------------------------------
FROM node:22-alpine AS production

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# `output: "standalone"` emits a minimal server bundle plus only the node_modules
# actually reachable at runtime.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
