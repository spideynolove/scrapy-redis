import json
import warnings

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False

from . import picklecompat


class JsonSerializer:
    """JSON serializer with UTF-8 encoding support for Redis storage."""
    
    @staticmethod
    def loads(data):
        """Load data from JSON bytes."""
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        return json.loads(data)

    @staticmethod
    def dumps(obj):
        """Dump object to JSON bytes."""
        return json.dumps(obj, ensure_ascii=False).encode('utf-8')


class MsgpackSerializer:
    """MessagePack serializer for compact binary serialization."""
    
    @staticmethod
    def loads(data):
        """Load data from MessagePack bytes."""
        if not HAS_MSGPACK:
            raise ImportError("msgpack is required for MsgpackSerializer")
        return msgpack.unpackb(data, raw=False)

    @staticmethod 
    def dumps(obj):
        """Dump object to MessagePack bytes."""
        if not HAS_MSGPACK:
            raise ImportError("msgpack is required for MsgpackSerializer")
        return msgpack.packb(obj)


class PickleSerializer:
    """Pickle serializer wrapper (deprecated - use for backward compatibility only)."""
    
    @staticmethod
    def loads(data):
        """Load data from pickle bytes."""
        warnings.warn(
            "Pickle serialization is deprecated for security reasons. "
            "Use 'json' or 'msgpack' serializers instead.",
            DeprecationWarning,
            stacklevel=3
        )
        return picklecompat.loads(data)

    @staticmethod
    def dumps(obj):
        """Dump object to pickle bytes."""
        warnings.warn(
            "Pickle serialization is deprecated for security reasons. "
            "Use 'json' or 'msgpack' serializers instead.", 
            DeprecationWarning,
            stacklevel=3
        )
        return picklecompat.dumps(obj)


# Registry of available serializers
SERIALIZERS = {
    'json': JsonSerializer,
    'msgpack': MsgpackSerializer,
    'pickle': PickleSerializer,
    'picklecompat': PickleSerializer,  # Alias for backward compatibility
}


def get_serializer(name_or_class):
    """Get serializer instance from name or class."""
    if isinstance(name_or_class, str):
        if name_or_class in SERIALIZERS:
            return SERIALIZERS[name_or_class]()
        else:
            # Try to import as module path
            try:
                import importlib
                module_path, class_name = name_or_class.rsplit('.', 1)
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                return cls()
            except (ValueError, ImportError, AttributeError):
                raise ValueError(f"Unknown serializer: {name_or_class}")
    elif hasattr(name_or_class, 'loads') and hasattr(name_or_class, 'dumps'):
        # Already a serializer instance
        return name_or_class
    else:
        raise TypeError(f"Invalid serializer type: {type(name_or_class)}")