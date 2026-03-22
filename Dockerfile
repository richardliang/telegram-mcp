# Use an official Python runtime as a parent image (Alpine-based for minimal vulnerabilities)
FROM python:3.13-alpine

# Set the working directory in the container
WORKDIR /app

# Prevent Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Ensure Python output is sent straight to terminal (useful for logs)
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY main.py .
COPY single_user_oauth.py .

# Create a non-root user and switch to it
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

# Define environment variables needed by the application
# These should be provided at runtime, not hardcoded (especially secrets)
ENV TELEGRAM_API_ID=""
ENV TELEGRAM_API_HASH=""
ENV TELEGRAM_SESSION_NAME="telegram_mcp_session"
ENV TELEGRAM_SESSION_STRING=""
ENV MCP_BIND_HOST="0.0.0.0"
ENV MCP_BIND_PORT="8000"
ENV MCP_PUBLIC_BASE_URL=""
ENV MCP_AUTH_USERNAME="admin"
ENV MCP_AUTH_PASSWORD="change-me"
ENV MCP_AUTH_SCOPE="user"
ENV MCP_ALLOWED_ROOTS=""

EXPOSE 8000

CMD ["python", "main.py"]
