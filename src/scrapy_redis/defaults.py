import redis

# For standalone use.
DUPEFILTER_KEY = "dupefilter:%(timestamp)s"

PIPELINE_KEY = "%(spider)s:items"

STATS_KEY = "%(spider)s:stats"

# Job-scoped key templates (new, job-aware)
JOB_SCOPED_PIPELINE_KEY = "%(job_id)s:%(spider)s:items"
JOB_SCOPED_STATS_KEY = "%(job_id)s:%(spider)s:stats"
JOB_SCOPED_SCHEDULER_QUEUE_KEY = "%(job_id)s:%(spider)s:requests"
JOB_SCOPED_SCHEDULER_DUPEFILTER_KEY = "%(job_id)s:%(spider)s:dupefilter"
JOB_SCOPED_START_URLS_KEY = "%(job_id)s:%(name)s:start_urls"

REDIS_CLS = redis.StrictRedis
REDIS_ENCODING = "utf-8"
# Sane connection defaults.
REDIS_PARAMS = {
    "socket_timeout": 30,
    "socket_connect_timeout": 30,
    "retry_on_timeout": True,
    "encoding": REDIS_ENCODING,
}
REDIS_CONCURRENT_REQUESTS = 16

SCHEDULER_QUEUE_KEY = "%(spider)s:requests"
SCHEDULER_QUEUE_CLASS = "scrapy_redis.queue.PriorityQueue"
SCHEDULER_DUPEFILTER_KEY = "%(spider)s:dupefilter"
SCHEDULER_DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RedisDupeFilter"
SCHEDULER_PERSIST = False
START_URLS_KEY = "%(name)s:start_urls"
START_URLS_AS_SET = False
START_URLS_AS_ZSET = False
MAX_IDLE_TIME = 0

# Feature flags and new settings
USE_JOB_SCOPED_KEYS = False
SCHEDULER_SERIALIZER = "json"  # "json", "msgpack", or "picklecompat" for legacy
PRIORITY_BLOCKING_ENABLED = "auto"  # auto|on|off
REQUEST_LEASE_SECONDS = 120
REQUEST_MAX_RETRIES = 5
DUPEFILTER_TTL_SECONDS = 604800  # 7 days
RETRY_SIMPLE_ENABLED = True
RETRY_SIMPLE_MAX = 3
RETRY_PRIORITY_ADJUST = -10  # Lower priority for retries
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]
PROMETHEUS_ENABLED = False
PROMETHEUS_PORT = 8000
