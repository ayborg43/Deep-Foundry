FROM mcr.microsoft.com/playwright:v1.61.1-noble@sha256:5b8f294aff9041b7191c34a4bab3ac270157a28774d4b0660e9743297b697e48

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev --ignore-scripts
COPY server.mjs /app/server.mjs
USER pwuser
EXPOSE 3001
CMD ["node", "/app/server.mjs"]
