FROM nginx:alpine
RUN apk add --no-cache dos2unix
COPY chat.html /usr/share/nginx/html/index.html
COPY entrypoint.sh /entrypoint.sh
RUN dos2unix /entrypoint.sh && chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
