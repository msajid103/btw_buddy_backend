#!/bin/bash

# Exit on error
set -o errexit  

# Collect static files
python manage.py collectstatic --noinput

# Apply database migrations
python manage.py migrate

# Start Gunicorn server
gunicorn btw_buddy_backend.wsgi:application --bind=0.0.0.0 --timeout 600
