from scrapy.utils.misc import load_object
from scrapy.utils.serialize import ScrapyJSONEncoder
from twisted.internet.threads import deferToThread

from . import connection, defaults
from .utils import get_effective_key

default_serialize = ScrapyJSONEncoder().encode


class RedisPipeline:
    """Pushes serialized item into a redis list/queue

    Settings
    --------
    REDIS_ITEMS_KEY : str
        Redis key where to store items.
    REDIS_ITEMS_SERIALIZER : str
        Object path to serializer function.

    """

    def __init__(
        self, server, key=defaults.PIPELINE_KEY, serialize_func=default_serialize, settings=None
    ):
        """Initialize pipeline.

        Parameters
        ----------
        server : StrictRedis
            Redis client instance.
        key : str
            Redis key where to store items.
        serialize_func : callable
            Items serializer function.
        settings : scrapy.settings.Settings, optional
            Settings for job-scoped key support

        """
        self.server = server
        self.key = key
        self.serialize = serialize_func
        self.settings = settings

    @classmethod
    def from_settings(cls, settings):
        params = {
            "server": connection.from_settings(settings),
            "settings": settings,
        }
        if settings.get("REDIS_ITEMS_KEY"):
            params["key"] = settings["REDIS_ITEMS_KEY"]
        if settings.get("REDIS_ITEMS_SERIALIZER"):
            params["serialize_func"] = load_object(settings["REDIS_ITEMS_SERIALIZER"])

        return cls(**params)

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings)

    def process_item(self, item, spider):
        return deferToThread(self._process_item, item, spider)

    def _process_item(self, item, spider):
        key = self.item_key(item, spider)
        data = self.serialize(item)
        self.server.rpush(key, data)
        return item

    def item_key(self, item, spider):
        """Returns redis key based on given spider.

        Override this function to use a different key depending on the item
        and/or spider.

        """
        if self.settings:
            return get_effective_key(
                self.settings,
                self.key,
                defaults.JOB_SCOPED_PIPELINE_KEY,
                spider.name
            )
        else:
            # Fallback for when settings is not available
            return self.key % {"spider": spider.name}
