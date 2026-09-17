from interarcade.app import app, socketio


if __name__ == "__main__":
    socketio.run(app, host=app.config["HOST"], port=app.config["PORT"])
