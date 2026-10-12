web: gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind ${HOST:-127.0.0.1}:${PORT:-5000} --timeout 120 --graceful-timeout 30 --keep-alive 5 app:app
worker: python -m interarcade.worker
