import os
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("VECTOR_STORE_PATH", "/tmp/test_vector_store")
os.environ.setdefault("UPLOAD_PATH", "/tmp/test_uploads")
