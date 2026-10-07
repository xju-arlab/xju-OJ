import math


class TokenBucket:
    """Consume submission capacity atomically across API workers in Redis."""

    _SCRIPT = """
        local clock = redis.call('TIME')
        local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
        local capacity, rate, initial, requested = tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), tonumber(ARGV[4])
        local old = redis.call('HMGET', KEYS[1], 'last_capacity', 'last_timestamp')
        local tokens = tonumber(old[1]) or initial
        local previous = tonumber(old[2]) or now
        tokens = math.min(capacity, tokens + math.max(0, now - previous) * rate)
        local allowed, wait = 0, 0
        if tokens >= requested then
            tokens = tokens - requested
            allowed = 1
        else
            wait = (requested - tokens) / rate
        end
        redis.call('HSET', KEYS[1], 'last_capacity', tokens, 'last_timestamp', now)
        redis.call('EXPIRE', KEYS[1], ARGV[5])
        return {allowed, tostring(wait)}
    """

    def __init__(self, key, capacity, fill_rate, default_capacity, redis_conn):
        if capacity <= 0 or fill_rate <= 0 or not 0 <= default_capacity <= capacity:
            raise ValueError("Invalid token bucket limits")
        self._key = key
        self._capacity = capacity
        self._fill_rate = fill_rate
        self._default_capacity = default_capacity
        self._redis_conn = redis_conn

    def consume(self, num=1):
        if not 0 < num <= self._capacity:
            raise ValueError("Invalid requested token count")
        allowed, wait = self._redis_conn.eval(
            self._SCRIPT, 1, self._key, self._capacity, self._fill_rate,
            self._default_capacity, num, max(60, math.ceil(self._capacity / self._fill_rate) * 2),
        )
        return bool(allowed), float(wait)
