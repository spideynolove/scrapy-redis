import json
import os
from json import JSONDecodeError

import six


class TextColor:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def bytes_to_str(s, encoding="utf-8"):
    """Returns a str if a bytes object is given."""
    if six.PY3 and isinstance(s, bytes):
        return s.decode(encoding)
    return s


def is_dict(string_content):
    """Try load string_content as json, if failed, return False, else return True."""
    try:
        json.loads(string_content)
    except JSONDecodeError:
        return False
    return True


def convert_bytes_to_str(data, encoding="utf-8"):
    """Convert a dict's keys & values from `bytes` to `str`
    or convert bytes to str"""
    if isinstance(data, bytes):
        return data.decode(encoding)
    if isinstance(data, dict):
        return dict(map(convert_bytes_to_str, data.items()))
    elif isinstance(data, tuple):
        return map(convert_bytes_to_str, data)
    return data


def get_redis_version(server):
    """Get Redis server version as tuple of integers."""
    try:
        info = server.info()
        version_str = info['redis_version']
        return tuple(int(x) for x in version_str.split('.'))
    except Exception:
        return (0, 0, 0)


def supports_bzpopmin(server):
    """Check if Redis server supports BZPOPMIN (requires Redis >= 5.0)."""
    version = get_redis_version(server)
    return version >= (5, 0, 0)


def expand_key_template(template, spider_name=None, job_id=None):
    """Expand key template with spider name and job_id if available."""
    params = {}
    
    if spider_name:
        params['spider'] = spider_name
        params['name'] = spider_name  # backwards compatibility
    
    if job_id:
        params['job_id'] = job_id
    
    # Add timestamp for legacy compatibility
    params['timestamp'] = int(__import__('time').time())
    
    try:
        return template % params
    except KeyError:
        # Missing required parameter, return template as-is
        return template


def get_job_id_from_settings(settings):
    """Get job_id from settings or environment."""
    job_id = settings.get('JOB_ID')
    if not job_id:
        job_id = os.environ.get('SCRAPY_JOB')
    return job_id


def get_effective_key(settings, legacy_key, job_scoped_key, spider_name=None):
    """Get the effective key based on whether job-scoped keys are enabled."""
    use_job_scoped = settings.getbool('USE_JOB_SCOPED_KEYS', False)
    job_id = get_job_id_from_settings(settings)
    
    if use_job_scoped and job_id:
        return expand_key_template(job_scoped_key, spider_name, job_id)
    else:
        return expand_key_template(legacy_key, spider_name, job_id)
