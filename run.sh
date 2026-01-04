#!/bin/bash

export NODE_ID=1
export PORT=8000
export HOST=http://192.168.56.103:8000


uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

