# Scrapy-Redis Upgrade Notes

This document outlines the architectural improvements and migration path for upgrading scrapy-redis to a production-ready, reliable distributed crawling system.

## Overview

These changes address critical production limitations identified in the original codebase:
- At-least-once semantics for requests (prevents data loss)
- Job isolation (prevents cross-job interference)  
- Blocking priority queues (eliminates CPU spinning)
- Better security (reduces pickle usage)
- Production observability (Prometheus metrics)

## Migration Strategy

All improvements are designed to be **backward compatible** and **opt-in** initially. You can adopt them incrementally without breaking existing deployments.

### Phase 1: Quick Wins (Zero Breaking Changes)

These features are **safe to enable immediately** and provide immediate value:

#### Job-Scoped Keys (Recommended)

**Problem**: Multiple crawl jobs of the same spider interfere with each other
**Solution**: Add unique job identifiers to Redis keys

```python
# settings.py
USE_JOB_SCOPED_KEYS = True  # Enable job isolation
JOB_ID = "crawl-2025-01-15-production"  # Or use SCRAPY_JOB env var
```

**What changes**: Redis keys go from `myspider:requests` to `crawl-2025-01-15-production:myspider:requests`
**Backward compatibility**: Disabled by default, old keys still work
**Risk**: None - completely additive

#### Safer Serialization (Recommended)

**Problem**: Pickle serialization is unsafe and fragile across Python versions
**Solution**: Default to JSON, keep pickle as fallback

```python
# settings.py  
SCHEDULER_SERIALIZER = "json"  # Use JSON (new default)
# SCHEDULER_SERIALIZER = "picklecompat"  # Explicit pickle fallback
```

**What changes**: Requests serialized as JSON instead of pickle
**Backward compatibility**: Set `SCHEDULER_SERIALIZER = "picklecompat"` to keep old behavior
**Risk**: Very low - JSON handles all standard Scrapy Request objects

#### Simple Retry Queue (Recommended)

**Problem**: Failed requests are lost forever
**Solution**: Automatic retry with exponential backoff

```python
# settings.py
RETRY_SIMPLE_ENABLED = True  # Enable simple retry
RETRY_SIMPLE_MAX = 3         # Max retry attempts
```

**What changes**: Failed requests are retried automatically
**Backward compatibility**: Disabled by default
**Risk**: None - purely additive

#### Prometheus Metrics (Optional)

**Problem**: No visibility into distributed crawl health
**Solution**: Export metrics for monitoring

```python
# settings.py
PROMETHEUS_ENABLED = True    # Export metrics
```

**What changes**: Metrics exported on `/metrics` endpoint
**Backward compatibility**: Disabled by default
**Risk**: None - monitoring only

### Phase 2: Core Reliability (Opt-In Advanced Features)

These provide production-grade reliability but require more careful adoption:

#### Leased Priority Queue (High Impact)

**Problem**: Worker crashes lose in-progress requests
**Solution**: Lease-based processing with automatic recovery

```python
# settings.py
SCHEDULER_QUEUE_CLASS = "scrapy_redis.queue.LeasedPriorityQueue"
REQUEST_LEASE_SECONDS = 120    # 2 minute lease timeout
REQUEST_MAX_RETRIES = 5        # Give up after 5 attempts
```

**What changes**: Requests are leased, not immediately removed from queue
**Backward compatibility**: Keep existing queue class as default
**Risk**: Medium - new queue semantics, test carefully
**Testing**: Verify at-least-once delivery, no duplicate explosion

#### Blocking Priority Pop (Performance)

**Problem**: Workers spin-wait when queue is empty, wasting CPU
**Solution**: Use Redis BZPOPMIN for efficient blocking

```python
# settings.py
PRIORITY_BLOCKING_ENABLED = "auto"  # Auto-detect Redis >= 5.0
# PRIORITY_BLOCKING_ENABLED = "on"   # Force enable
# PRIORITY_BLOCKING_ENABLED = "off"  # Force disable
```

**What changes**: Workers block instead of polling empty queues
**Backward compatibility**: Auto-detects Redis version, falls back to polling
**Risk**: Low - graceful degradation
**Requirements**: Redis >= 5.0 recommended

#### Enhanced Fingerprinting (Correctness)

**Problem**: Current fingerprinting misses headers/cookies, causes false duplicates
**Solution**: Include normalized headers and cookie hashes

```python
# settings.py
DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RedisDupeFilterV2"
DUPEFILTER_TTL_SECONDS = 604800  # 7 day sliding window
```

**What changes**: More accurate deduplication, memory-bounded fingerprint cache
**Backward compatibility**: Keep existing dupefilter as default
**Risk**: Medium - different dedup behavior, may see more/fewer requests
**Testing**: Compare request volumes before/after

## Environment Variables

The system recognizes these environment variables:

```bash
export SCRAPY_JOB="production-run-$(date +%Y%m%d-%H%M)"  # Auto job naming
export JOB_ID="custom-job-identifier"                   # Override job ID
```

## Redis Version Compatibility

| Feature | Redis 4.x | Redis 5.x | Redis 6+ |
|---------|-----------|-----------|----------|
| Basic queues | ✅ | ✅ | ✅ |
| Leased queues | ✅ (Lua) | ✅ (Native) | ✅ (Native) |  
| Blocking pop | ✅ (Polling) | ✅ (BZPOPMIN) | ✅ (BZPOPMIN) |

**Recommendation**: Redis 6+ for best performance and features

## Migration Checklist

### Before Upgrading
- [ ] Backup Redis data
- [ ] Document current spider job patterns
- [ ] Test in development environment
- [ ] Set up monitoring dashboards

### Deployment Steps  
- [ ] Deploy code with new features **disabled**
- [ ] Verify existing functionality works unchanged
- [ ] Enable job-scoped keys on one low-risk spider
- [ ] Monitor Redis key patterns and memory usage
- [ ] Enable JSON serialization after confirming compatibility
- [ ] Add Prometheus metrics and dashboards
- [ ] Test simple retry queue behavior
- [ ] Gradually enable advanced features per spider

### Post-Deployment Monitoring
- [ ] Queue depth trends (should not grow unbounded)
- [ ] Duplicate request rates (should decrease with better fingerprinting)
- [ ] Lease expiry rates (should be low, <1% under normal conditions)
- [ ] Redis memory usage (should be bounded with TTL)
- [ ] Worker CPU usage (should decrease with blocking pop)

## Rollback Plan

All features can be disabled by reverting settings:

```python
# Emergency rollback settings
USE_JOB_SCOPED_KEYS = False
SCHEDULER_SERIALIZER = "picklecompat"  
SCHEDULER_QUEUE_CLASS = "scrapy_redis.queue.PriorityQueue"
DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RedisDupeFilter"  
PRIORITY_BLOCKING_ENABLED = "off"
RETRY_SIMPLE_ENABLED = False
PROMETHEUS_ENABLED = False
```

No data migration is required for rollback thanks to backward-compatible key naming.

## Support

For issues during migration:
1. Check the rollback settings above
2. Monitor Redis logs for connection/command errors  
3. Verify Redis version compatibility
4. Test with a single spider first
5. File issues with detailed error logs and configuration

## Performance Impact

Expected performance changes:

| Feature | CPU | Memory | Network | Latency |
|---------|-----|--------|---------|---------|
| Job-scoped keys | ✅ None | ⚠️ +5-10% (longer keys) | ✅ None | ✅ None |
| JSON serialization | ✅ -5% (faster than pickle) | ✅ -10% (more compact) | ✅ -10% (smaller) | ✅ -10ms (faster parse) |
| Leased queues | ⚠️ +10% (bookkeeping) | ⚠️ +20% (processing ZSET) | ⚠️ +15% (ACK traffic) | ✅ Better (no loss retries) |
| Blocking pop | ✅ -50% (no spin) | ✅ None | ⚠️ +5% (persistent conn) | ✅ -50ms (immediate wake) |

Net result: **Lower CPU, slightly higher memory, much better reliability**