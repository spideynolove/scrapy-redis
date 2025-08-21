import logging
import time
from scrapy import signals
from scrapy.exceptions import IgnoreRequest, NotConfigured
from twisted.internet.error import TimeoutError, DNSLookupError, ConnectionRefusedError, ConnectionDone, ConnectError, ConnectionLost

from . import defaults


class SimpleRedisRetryMiddleware:
    """Simple retry middleware that puts failed requests back into Redis queue.
    
    This is a simpler version that doesn't use leasing - just tracks retry count
    and puts requests back with exponential backoff delay via priority adjustment.
    """
    
    EXCEPTIONS_TO_RETRY = (
        TimeoutError,
        DNSLookupError, 
        ConnectionRefusedError,
        ConnectionDone,
        ConnectError,
        ConnectionLost,
    )
    
    def __init__(self, settings):
        if not settings.getbool('RETRY_SIMPLE_ENABLED', defaults.RETRY_SIMPLE_ENABLED):
            raise NotConfigured('Simple retry middleware not enabled')
            
        self.max_retry_times = settings.getint('RETRY_SIMPLE_MAX', defaults.RETRY_SIMPLE_MAX)
        self.retry_http_codes = set(int(x) for x in settings.getlist('RETRY_HTTP_CODES', [500, 502, 503, 504, 408, 429]))
        self.priority_adjust = settings.getint('RETRY_PRIORITY_ADJUST', -10)  # Lower priority for retries
        
        # We'll store the scheduler reference to requeue requests
        self.scheduler = None
        
        self.logger = logging.getLogger(__name__)
        
    @classmethod
    def from_crawler(cls, crawler):
        instance = cls(crawler.settings)
        crawler.signals.connect(instance.spider_opened, signal=signals.spider_opened)
        return instance
        
    def spider_opened(self, spider):
        """Get reference to scheduler for requeuing."""
        self.scheduler = spider.crawler.engine.scheduler
        
    def process_response(self, request, response, spider):
        """Process response and retry if needed."""
        if response.status in self.retry_http_codes:
            reason = f'status {response.status}'
            return self._retry(request, reason, spider) or response
        return response
        
    def process_exception(self, request, exception, spider):
        """Process exceptions and retry if retryable."""
        if isinstance(exception, self.EXCEPTIONS_TO_RETRY):
            return self._retry(request, f'{exception.__class__.__name__}: {exception}', spider)
        elif isinstance(exception, IgnoreRequest):
            return self._retry(request, 'ignored request', spider)
            
    def _retry(self, request, reason, spider):
        """Retry request by putting it back in the queue."""
        retry_count = request.meta.get('retry_count', 0)
        
        if retry_count >= self.max_retry_times:
            self.logger.debug(
                f"Gave up retrying %(request)s (failed {retry_count} times): %(reason)s",
                {'request': request, 'reason': reason}, extra={'spider': spider}
            )
            # Could put in dead letter queue here in the future
            return None
            
        # Create retry request with incremented count and adjusted priority
        retry_count += 1
        retry_request = request.replace(
            meta=request.meta.copy()
        )
        retry_request.meta['retry_count'] = retry_count
        retry_request.meta['retry_reason'] = reason
        retry_request.meta['retry_time'] = time.time()
        
        # Adjust priority - lower priority for retries with exponential backoff
        # Each retry gets progressively lower priority
        original_priority = getattr(request, 'priority', 0)
        backoff_factor = 2 ** (retry_count - 1)  # 1, 2, 4, 8, ...
        retry_request.priority = original_priority + (self.priority_adjust * backoff_factor)
        
        # Put back in scheduler queue if available
        if self.scheduler and hasattr(self.scheduler, 'enqueue_request'):
            if self.scheduler.enqueue_request(retry_request):
                self.logger.debug(
                    f"Retrying %(request)s (failed {retry_count-1} times, retry #{retry_count}): %(reason)s",
                    {'request': retry_request, 'reason': reason}, extra={'spider': spider}
                )
            else:
                self.logger.debug(
                    f"Failed to requeue retry request %(request)s: %(reason)s", 
                    {'request': retry_request, 'reason': reason}, extra={'spider': spider}
                )
        else:
            self.logger.warning(
                f"No scheduler available for retry: %(request)s",
                {'request': retry_request}, extra={'spider': spider}
            )
            
        return None  # Don't continue processing the original request


class RedisRetryStatsCollector:
    """Collect retry-related statistics for monitoring."""
    
    def __init__(self, stats):
        self.stats = stats
        
    def retry_attempted(self, request, spider):
        """Record retry attempt."""
        self.stats.inc_value('retry/count', spider=spider)
        retry_count = request.meta.get('retry_count', 0)
        self.stats.inc_value(f'retry/count_{retry_count}', spider=spider)
        
    def retry_gave_up(self, request, spider):
        """Record when we give up on a request."""
        self.stats.inc_value('retry/gave_up', spider=spider)
        
    def retry_requeued(self, request, spider):
        """Record successful requeue."""
        self.stats.inc_value('retry/requeued', spider=spider)