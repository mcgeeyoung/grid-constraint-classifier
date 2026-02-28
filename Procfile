web: gunicorn app.main:app -k uvicorn.workers.UvicornWorker --workers 3 --bind 0.0.0.0:$PORT
worker: python -m app.scheduler
