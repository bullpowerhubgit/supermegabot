FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install --production

COPY . .

# Cloud Run erwartet einen Port
ENV PORT=8080

CMD ["node", "cloud-automation.js"]
