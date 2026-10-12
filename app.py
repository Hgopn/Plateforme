from interarcade.app import create_app, socketio


app = create_app()


if __name__ == "__main__":
    # Development-only entrypoint. Integration/production uses Gunicorn with
    # the gevent WebSocket worker from deploy/docker-compose.integration.yml.
    socketio.run(
        app,
        host=app.config["HOST"],
        port=app.config["PORT"],
        allow_unsafe_werkzeug=True,
    )
