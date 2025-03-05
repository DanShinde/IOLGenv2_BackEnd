FROM python:3.12

# Ensure Python output is not buffered
ENV PYTHONUNBUFFERED=1

# Set working directory inside the container
WORKDIR /app

# Copy dependencies list to container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application to the container
COPY . .

# Create static directory
RUN mkdir -p /app/static

# Collect static files during image build
RUN python manage.py collectstatic --noinput


# Expose the port your application will run on
EXPOSE 8000

# Default command to run the application
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
