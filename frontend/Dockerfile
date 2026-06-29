# Сборка React-приложения и отдача статики через nginx.
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Адрес backend зашивается в бандл на этапе сборки (Vite-переменная).
# На сервере задать в .env: VITE_API_URL=http://<адрес-сервера>:8000
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
