import os

# Settings are read at import time, so the environment must exist before app import.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("GIT_SHA", "testsha")
os.environ.setdefault("SECRET_KEY", "test-secret")
