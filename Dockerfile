# FROM python:3.12

# # Ensure Python output is not buffered
# ENV PYTHONUNBUFFERED=1

# # Set working directory inside the container
# WORKDIR /app

# # Copy dependencies list to container
# COPY requirements.txt .

# # Install dependencies
# RUN pip install --no-cache-dir -r requirements.txt

# # Copy the entire application to the container
# COPY . .

# # Create static directory
# RUN mkdir -p /app/static

# # # Collect static files during image build
# # RUN python manage.py collectstatic --noinput


# # Expose the port your application will run on
# EXPOSE 8000

# # Default command to run the application
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Use a slim Python image to reduce size
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies (needed for PostgreSQL, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy and install Python dependencies first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Collect static files (Render expects them in `/app/static`)
RUN python manage.py collectstatic --noinput

# Run as a non-root user (security best practice)
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose the port Render will use (8000 by default)
EXPOSE 8000

# Start Gunicorn (production-ready WSGI server)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "IOLGenv2_BackEnd.wsgi:application"]