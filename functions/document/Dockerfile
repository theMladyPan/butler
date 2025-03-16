# Use the official Python image.
# https://hub.docker.com/_/python
FROM python:3.12-alpine

# Copy local code to the container image.
ENV APP_HOME /app
ENV PYTHONUNBUFFERED TRUE

WORKDIR $APP_HOME
COPY . .
COPY .env .

# Install SQLite3 for qdrant
RUN apk add --no-cache sqlite sqlite-dev  

# Install production dependencies.
RUN pip install functions-framework
RUN pip install -r requirements.txt

# Run the web service on container startup
CMD ["functions-framework", "--target=on_document"]