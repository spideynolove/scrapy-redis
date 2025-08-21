from collections import defaultdict

try:
    from prometheus_client import CollectorRegistry, generate_latest
    from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

from .connection import from_settings as redis_from_settings
from . import defaults


class RedisStatsCollector:
    """Prometheus collector that reads stats from Redis and exposes them as metrics."""
    
    def __init__(self, server, stats_key_pattern=None):
        self.server = server
        self.stats_key_pattern = stats_key_pattern or defaults.STATS_KEY
        
    def collect(self):
        """Collect metrics from Redis stats keys."""
        if not HAS_PROMETHEUS:
            return
            
        # Find all stats keys matching the pattern
        stats_keys = self.server.keys(self.stats_key_pattern.replace('%(spider)s', '*'))
        
        # Group metrics by type
        counter_metrics = defaultdict(dict)
        gauge_metrics = defaultdict(dict)
        
        for key in stats_keys:
            # Extract spider name from key
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            spider_name = self._extract_spider_name(key_str)
            
            # Get all stats for this spider
            stats = self.server.hgetall(key)
            if not stats:
                continue
                
            for metric_name, value in stats.items():
                metric_name_str = metric_name.decode('utf-8') if isinstance(metric_name, bytes) else metric_name
                value_str = value.decode('utf-8') if isinstance(value, bytes) else value
                
                try:
                    numeric_value = float(value_str)
                except ValueError:
                    continue
                    
                # Categorize metrics
                if self._is_counter_metric(metric_name_str):
                    counter_metrics[metric_name_str][spider_name] = numeric_value
                else:
                    gauge_metrics[metric_name_str][spider_name] = numeric_value
        
        # Yield counter metrics
        for metric_name, spider_values in counter_metrics.items():
            family = CounterMetricFamily(
                f'scrapy_redis_{metric_name}',
                f'Scrapy Redis {metric_name}',
                labels=['spider']
            )
            for spider_name, value in spider_values.items():
                family.add_metric([spider_name], value)
            yield family
            
        # Yield gauge metrics  
        for metric_name, spider_values in gauge_metrics.items():
            family = GaugeMetricFamily(
                f'scrapy_redis_{metric_name}',
                f'Scrapy Redis {metric_name}',
                labels=['spider']
            )
            for spider_name, value in spider_values.items():
                family.add_metric([spider_name], value)
            yield family
    
    def _extract_spider_name(self, key):
        """Extract spider name from Redis key."""
        # Handle both job-scoped and regular keys
        # job-scoped: "job123:myspider:stats" -> "myspider"  
        # regular: "myspider:stats" -> "myspider"
        parts = key.split(':')
        if len(parts) >= 3 and parts[-1] == 'stats':
            return parts[-2]  # spider name is second to last
        elif len(parts) >= 2 and parts[-1] == 'stats':
            return parts[-2]  # spider name is second to last
        else:
            return 'unknown'
    
    def _is_counter_metric(self, metric_name):
        """Determine if a metric should be treated as a counter (monotonically increasing)."""
        counter_patterns = [
            'downloader/request_count',
            'downloader/response_count', 
            'downloader/exception_count',
            'item_scraped_count',
            'response_received_count',
            'scheduler/enqueued',
            'scheduler/dequeued',
            'spider_opened_count',
            'spider_closed_count'
        ]
        return any(pattern in metric_name for pattern in counter_patterns)


class PrometheusStatsExporter:
    """HTTP server that exposes Scrapy Redis stats as Prometheus metrics."""
    
    def __init__(self, settings, port=8000):
        if not HAS_PROMETHEUS:
            raise ImportError("prometheus_client is required for PrometheusStatsExporter")
            
        self.port = port
        self.server = redis_from_settings(settings)
        self.stats_key_pattern = settings.get('STATS_KEY', defaults.STATS_KEY)
        
        # Create custom registry with our collector
        self.registry = CollectorRegistry()
        self.collector = RedisStatsCollector(self.server, self.stats_key_pattern)
        self.registry.register(self.collector)
        
    def start_server(self):
        """Start HTTP server to serve metrics."""
        try:
            from prometheus_client import start_http_server
            start_http_server(self.port, registry=self.registry)
            return True
        except ImportError:
            return False
            
    def get_metrics_text(self):
        """Get metrics in Prometheus text format."""
        return generate_latest(self.registry)


def create_scrapy_extension(crawler):
    """Create Scrapy extension for Prometheus metrics export."""
    
    class PrometheusExtension:
        """Scrapy extension that exports metrics to Prometheus."""
        
        def __init__(self, crawler):
            self.crawler = crawler
            self.settings = crawler.settings
            self.enabled = self.settings.getbool('PROMETHEUS_ENABLED', defaults.PROMETHEUS_ENABLED)
            self.port = self.settings.getint('PROMETHEUS_PORT', 8000)
            self.exporter = None
            
        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler)
            
        def spider_opened(self, spider):
            if not self.enabled:
                return
                
            if not HAS_PROMETHEUS:
                spider.logger.warning("prometheus_client not installed, metrics export disabled")
                return
                
            try:
                self.exporter = PrometheusStatsExporter(self.settings, self.port)
                if self.exporter.start_server():
                    spider.logger.info(f"Prometheus metrics server started on port {self.port}")
                else:
                    spider.logger.warning("Failed to start Prometheus metrics server")
            except Exception as e:
                spider.logger.error(f"Error starting Prometheus exporter: {e}")
                
        def spider_closed(self, spider, reason):
            if self.exporter:
                spider.logger.info("Prometheus metrics export stopped")
    
    return PrometheusExtension(crawler)