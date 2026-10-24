"""Use one serial worker: sessions are in memory and not thread-safe."""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
worker_class = "sync"
threads = 1
timeout = 60
accesslog = "-"
errorlog = "-"
# Exclude query strings, which can contain admin credentials.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'
