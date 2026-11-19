@echo off
setlocal

python -m waitress --host=0.0.0.0 --port=5000 backend.app:app
