"""Production WSGI entry point for BharatEdge Dashboard."""

from monitoring.dashboard import create_app

app = create_app()
server = app.server
