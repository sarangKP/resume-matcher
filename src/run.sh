#!/bin/bash
# Lambda Web Adapter runs this as the "handler" and sends requests to the port below.
PATH=$PATH:$LAMBDA_TASK_ROOT/bin PYTHONPATH=$PYTHONPATH:/opt/python:$LAMBDA_RUNTIME_DIR exec python -m uvicorn --port=$PORT app:app
