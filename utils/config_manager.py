"""
ConfigManager: Thread-safe, cached configuration management utility.

Provides singleton pattern with in-memory caching, debounced saves,
and atomic file operations to eliminate repeated file I/O.
"""
import os
import json
import asyncio
import threading
from typing import Dict, Any, Optional, Callable
from pathlib import Path
from datetime import datetime


class ConfigManager:
    """
    Singleton configuration manager with caching and thread-safety.
    
    Features:
    - In-memory cache with dirty flag tracking
    - Thread-safe access with locks
    - Debounced saves (batches multiple updates)
    - Atomic file writes with backup
    - Change notification callbacks
    """
    
    _instance: Optional['ConfigManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._config_cache: Dict[str, Any] = {}
        self._config_path: Optional[str] = None
        self._dirty = False
        self._save_task: Optional[asyncio.Task] = None
        self._save_delay = 0.5  # Debounce delay in seconds
        self._callbacks: list[Callable[[Dict[str, Any]], None]] = []
        self._access_lock = asyncio.Lock()
        self._thread_lock = threading.Lock()  # Separate lock for synchronous operations
        
    def initialize(self, config_path: str, default_factory: Optional[Callable[[], Dict[str, Any]]] = None):
        """
        Initialize the config manager with a file path.
        
        Args:
            config_path: Path to the JSON config file
            default_factory: Optional function that returns default config dict
        """
        self._config_path = config_path
        self._default_factory = default_factory or (lambda: {})
        
        # Load initial config
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f) or self._default_factory()
            except Exception:
                self._config_cache = self._default_factory()
        else:
            self._config_cache = self._default_factory()
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get a config value (cached, no file I/O)."""
        async with self._access_lock:
            return self._config_cache.get(key, default)
    
    async def set(self, key: str, value: Any, save_immediately: bool = False):
        """
        Set a config value and schedule a save.
        
        Args:
            key: Config key
            value: Value to set
            save_immediately: If True, save immediately instead of debouncing
        """
        async with self._access_lock:
            self._config_cache[key] = value
            self._dirty = True
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(self._config_cache)
                except Exception:
                    pass
        
        if save_immediately:
            await self.save_now()
        else:
            await self._schedule_save()
    
    async def update(self, updates: Dict[str, Any], save_immediately: bool = False):
        """
        Update multiple config values at once.
        
        Args:
            updates: Dictionary of key-value pairs to update
            save_immediately: If True, save immediately instead of debouncing
        """
        async with self._access_lock:
            self._config_cache.update(updates)
            self._dirty = True
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(self._config_cache)
                except Exception:
                    pass
        
        if save_immediately:
            await self.save_now()
        else:
            await self._schedule_save()
    
    async def get_all(self) -> Dict[str, Any]:
        """Get entire config (returns a copy)."""
        async with self._access_lock:
            return self._config_cache.copy()
    
    async def _schedule_save(self):
        """Schedule a debounced save operation."""
        # Cancel existing save task if any
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        
        # Schedule new save
        self._save_task = asyncio.create_task(self._debounced_save())
    
    async def _debounced_save(self):
        """Wait for the debounce delay, then save."""
        try:
            await asyncio.sleep(self._save_delay)
            await self.save_now()
        except asyncio.CancelledError:
            pass
    
    async def save_now(self):
        """Save config immediately with atomic write."""
        if not self._dirty or not self._config_path:
            return
        
        async with self._access_lock:
            try:
                # Create backup if file exists
                if os.path.exists(self._config_path):
                    backup_path = f"{self._config_path}.backup"
                    try:
                        import shutil
                        shutil.copy2(self._config_path, backup_path)
                    except Exception:
                        pass
                
                # Write to temp file first (atomic operation)
                temp_path = f"{self._config_path}.tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._config_cache, f, ensure_ascii=False, indent=2)
                
                # Atomic rename
                os.replace(temp_path, self._config_path)
                self._dirty = False
                
            except Exception as e:
                # Log error but don't raise
                print(f"ConfigManager: Failed to save config: {e}")
    
    def register_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register a callback to be called when config changes."""
        self._callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Unregister a previously registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    async def reload(self):
        """Force reload config from disk (use sparingly)."""
        if not self._config_path or not os.path.exists(self._config_path):
            return
        
        async with self._access_lock:
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._config_cache = json.load(f) or self._default_factory()
                self._dirty = False
            except Exception:
                pass
    
    # Synchronous versions for backward compatibility
    def get_sync(self, key: str, default: Any = None) -> Any:
        """Synchronous get (for non-async contexts)."""
        with self._thread_lock:
            return self._config_cache.get(key, default)
    
    def set_sync(self, key: str, value: Any):
        """Synchronous set (schedules async save)."""
        with self._thread_lock:
            self._config_cache[key] = value
            self._dirty = True
            # Note: actual save will happen async
    
    def update_sync(self, updates: Dict[str, Any]):
        """Synchronous update multiple values."""
        with self._thread_lock:
            self._config_cache.update(updates)
            self._dirty = True
    
    def save_sync(self):
        """Synchronous save (immediate, blocking)."""
        if not self._dirty or not self._config_path:
            return
        
        with self._thread_lock:
            try:
                # Create backup if file exists
                if os.path.exists(self._config_path):
                    backup_path = f"{self._config_path}.backup"
                    try:
                        import shutil
                        shutil.copy2(self._config_path, backup_path)
                    except Exception:
                        pass
                
                # Write to temp file first (atomic operation)
                temp_path = f"{self._config_path}.tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._config_cache, f, ensure_ascii=False, indent=2)
                
                # Atomic rename
                os.replace(temp_path, self._config_path)
                self._dirty = False
                
            except Exception as e:
                # Log error but don't raise
                print(f"ConfigManager: Failed to save config: {e}")
    
    def get_all_sync(self) -> Dict[str, Any]:
        """Synchronous get all (for non-async contexts)."""
        with threading.Lock():
            return self._config_cache.copy()


# Convenience function for getting singleton instance
def get_config_manager() -> ConfigManager:
    """Get the singleton ConfigManager instance."""
    return ConfigManager()
