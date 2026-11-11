"""WSGI production entrypoint for Gunicorn / container deployments."""
from app import app

if __name__ == "__main__":
    app.run()
