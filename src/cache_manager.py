import os
import json
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime

class CacheManager:
    """Manage upgrade cache and resume capability"""
    
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.cache_dir = os.path.join(repo_path, ".ml_upgrader_cache")
        self.cache_file = os.path.join(self.cache_dir, "upgrade_cache.json")
        self.cache_data = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """Load existing cache or create new"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Could not load cache: {e}")
                return {"files": {}, "metadata": {}}
        return {"files": {}, "metadata": {}}
    
    def _save_cache(self):
        """Persist cache to disk"""
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache_data, f, indent=2)
    
    def _get_file_hash(self, file_path: str) -> str:
        """Get MD5 hash of file content"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def is_file_cached(self, file_path: str) -> bool:
        """Check if file was already successfully upgraded"""
        rel_path = os.path.relpath(file_path, self.repo_path)
        
        if rel_path not in self.cache_data["files"]:
            return False
        
        cached_entry = self.cache_data["files"][rel_path]
        
        # Check if file hasn't changed since cache
        current_hash = self._get_file_hash(file_path)
        cached_hash = cached_entry.get("input_hash", "")
        
        if current_hash != cached_hash:
            print(f"{rel_path} changed since cache, re-upgrading")
            return False
        
        # Check if upgrade was successful
        if not cached_entry.get("success", False):
            return False
        
        return True
    
    def cache_result(self, file_path: str, result: Any, upgraded_code: Optional[str] = None):
        """Cache upgrade result for a file"""
        rel_path = os.path.relpath(file_path, self.repo_path)
        
        self.cache_data["files"][rel_path] = {
            "success": result.success,
            "attempts": result.attempts,
            "timestamp": datetime.now().isoformat(),
            "input_hash": self._get_file_hash(file_path),
            "error": result.error,
            "api_changes": result.api_changes
        }
        
        # Save upgraded code to cache for quick restore
        if upgraded_code and result.success:
            code_cache_path = os.path.join(self.cache_dir, "upgraded", rel_path)
            os.makedirs(os.path.dirname(code_cache_path), exist_ok=True)
            with open(code_cache_path, 'w') as f:
                f.write(upgraded_code)
            self.cache_data["files"][rel_path]["cached_output"] = code_cache_path
        
        self._save_cache()
    
    def restore_from_cache(self, file_path: str, output_path: str) -> bool:
        """Restore upgraded file from cache"""
        rel_path = os.path.relpath(file_path, self.repo_path)
        
        if rel_path not in self.cache_data["files"]:
            return False
        
        cached_entry = self.cache_data["files"][rel_path]
        cached_output = cached_entry.get("cached_output")
        
        if not cached_output or not os.path.exists(cached_output):
            return False
        
        try:
            with open(cached_output, 'r') as f:
                content = f.read()
            with open(output_path, 'w') as f:
                f.write(content)
            print(f"Restored {rel_path} from cache")
            return True
        except Exception as e:
            print(f"  ⚠️ Failed to restore from cache: {e}")
            return False
    
    def get_cached_result(self, file_path: str) -> Optional[Dict]:
        """Get cached result for a file"""
        rel_path = os.path.relpath(file_path, self.repo_path)
        return self.cache_data["files"].get(rel_path)
    
    def clear_cache(self):
        """Clear all cache data"""
        if os.path.exists(self.cache_dir):
            import shutil
            shutil.rmtree(self.cache_dir)
        self.cache_data = {"files": {}, "metadata": {}}
        print("Cache cleared")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total = len(self.cache_data["files"])
        successful = sum(1 for f in self.cache_data["files"].values() if f.get("success"))
        failed = total - successful
        
        return {
            "total_cached": total,
            "successful": successful,
            "failed": failed
        }