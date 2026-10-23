# ==============================================================================
# Production Dockerfile for HIAS React / Vite Frontend
# ==============================================================================

# Stage 1: Build the React static bundle
FROM node:20-alpine AS builder

WORKDIR /app

# Optional build argument without exposing hardcoded secrets or URLs as defaults
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

# Copy package manifests and install dependencies
COPY package*.json ./
RUN npm ci || npm install

# Copy source code and build
COPY . .
RUN npm run build

# Stage 2: Serve static distribution via lightweight Node serve utility
FROM node:20-alpine

WORKDIR /app

RUN npm install -g serve

COPY --from=builder /app/dist ./dist

# Create dedicated non-root user for production security compliance
RUN adduser --disabled-password --gecos "" frontend && \
    chown -R frontend:frontend /app

USER frontend

# Native internal frontend port
EXPOSE 5173

HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=5s \
    CMD wget -q --spider http://localhost:5173/ || exit 1

CMD ["serve", "-s", "dist", "-l", "5173"]
