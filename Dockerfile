# SuperMegaBot Dashboard Server Dockerfile
FROM node:20-alpine

WORKDIR /app

# Install Python for mac_optimizer module fallback support
RUN apk add --no-cache python3 py3-pip zip tar curl

COPY package*.json ./
RUN npm ci --only=production

COPY . .

# Ensure data and logs directories exist
RUN mkdir -p data logs backups

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8888/api/health || exit 1

CMD ["node", "server.js"]
