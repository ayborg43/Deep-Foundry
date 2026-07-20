FROM python:3.14-alpine

RUN addgroup -S proxy && adduser -S -G proxy proxy
WORKDIR /app
COPY proxy.py /app/proxy.py
USER proxy
EXPOSE 8080
CMD ["python", "/app/proxy.py"]

