# Этап 1: Сборка статики
FROM node:alpine AS build

WORKDIR /app

# Копируем package.json и опционально package-lock.json (символ * делает файл необязательным)
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# Этап 2: Раздача статики через легковесный веб-сервер Nginx
FROM nginx:alpine

# Копируем собранное React-приложение из первого этапа в директорию Nginx
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]