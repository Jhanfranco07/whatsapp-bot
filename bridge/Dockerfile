FROM node:22-bookworm-slim

WORKDIR /bridge

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      chromium \
      fonts-liberation \
      libasound2 \
      libatk-bridge2.0-0 \
      libatk1.0-0 \
      libcups2 \
      libdrm2 \
      libgbm1 \
      libgtk-3-0 \
      libnss3 \
      libxcomposite1 \
      libxdamage1 \
      libxrandr2 \
      xdg-utils \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

CMD ["npm", "start"]
