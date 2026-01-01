# -*- coding: utf-8 -*-
"""
V9升级：三级缓存系统
L1: 内存缓存（热数据）
L2: SQLite缓存（温数据）  
L3: API调用（智能限流）
"""

import time
import json
import sqlite3
import hashlib
import threading
from collections import OrderedDict
from typing import Any, Optional, Callable
from functools import wraps

class LRUCache:
    """L1 内存LRU缓存"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 60):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache = OrderedDict()
        self._timestamps = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            if time.time() - self._timestamps.get(key, 0) > self.default_ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return self._cache[key]
    
    def set(self, key: str, value: Any, ttl: int = None):
        with self._lock:
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            self._cache[key] = value
            self._timestamps[key] = time.time()
    
    def delete(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

class SQLiteCache:
    """L2 SQLite缓存"""
    
    def __init__(self, db_path: str = "cache.db", default_ttl: int = 3600):
        self.db_path = db_path
        self.default_ttl = default_ttl
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl INTEGER NOT NULL
                )
            """)
            conn.execute("DELETE FROM cache WHERE created_at + ttl < ?", (time.time(),))
    
    def get(self, key: str) -> Optional[Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value, created_at, ttl FROM cache WHERE key=?", (key,)).fetchone()
            if row and time.time() - row[1] <= row[2]:
                return json.loads(row[0])
        return None
    
    def set(self, key: str, value: Any, ttl: int = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)",
                (key, json.dumps(value, ensure_ascii=False, default=str), time.time(), ttl or self.default_ttl))

class RateLimiter:
    """API限流器"""
    
    def __init__(self, rate: int = 180, per: int = 60):
        self.rate = rate
        self.per = per
        self.tokens = rate
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def acquire(self) -> bool:
        with self._lock:
            now = time.time()
            self.tokens = min(self.rate, self.tokens + (now - self.last_update) * self.rate / self.per)
            self.last_update = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False
    
    def wait(self):
        while not self.acquire():
            time.sleep(0.1)

class ThreeLevelCache:
    """三级缓存管理器"""
    
    def __init__(self):
        self.l1 = LRUCache(max_size=2000, default_ttl=120)
        self.l2 = SQLiteCache(db_path="v9_cache.db", default_ttl=7200)
        self.limiter = RateLimiter(rate=180)
        self._stats = {"l1_hits": 0, "l2_hits": 0, "api_calls": 0}
    
    def get(self, key: str, api_fallback: Callable = None, l1_ttl: int = 120, l2_ttl: int = 3600):
        # L1
        val = self.l1.get(key)
        if val is not None:
            self._stats["l1_hits"] += 1
            return val
        
        # L2
        val = self.l2.get(key)
        if val is not None:
            self._stats["l2_hits"] += 1
            self.l1.set(key, val, l1_ttl)
            return val
        
        # L3 API
        if api_fallback:
            self.limiter.wait()
            try:
                val = api_fallback()
                self._stats["api_calls"] += 1
                if val is not None:
                    self.l1.set(key, val, l1_ttl)
                    self.l2.set(key, val, l2_ttl)
                return val
            except Exception as e:
                print(f"API error: {e}")
        return None
    
    def set(self, key: str, value: Any):
        self.l1.set(key, value)
        self.l2.set(key, value)
    
    @property
    def stats(self):
        return self._stats

# 全局缓存实例
cache = ThreeLevelCache()
