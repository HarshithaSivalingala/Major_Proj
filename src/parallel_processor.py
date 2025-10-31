import asyncio
import time
from typing import List, Callable, Any, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import threading

class RateLimiter:
    """Token bucket rate limiter for API calls"""
    
    def __init__(self, max_calls: int, time_window: float):
        """
        max_calls: Maximum number of calls allowed in time_window
        time_window: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
        self.lock = threading.Lock()
    
    def acquire(self) -> float:
        """
        Attempt to acquire permission to make a call
        Returns: wait time in seconds (0 if can proceed immediately)
        """
        with self.lock:
            now = time.time()
            
            # Remove calls outside the time window
            while self.calls and self.calls[0] < now - self.time_window:
                self.calls.popleft()
            
            # Check if we can make a call
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return 0.0
            
            # Calculate wait time
            oldest_call = self.calls[0]
            wait_time = (oldest_call + self.time_window) - now
            return max(0.0, wait_time)
    
    async def wait_if_needed(self):
        """Async wait for rate limit"""
        wait_time = self.acquire()
        if wait_time > 0:
            await asyncio.sleep(wait_time)


class ParallelProcessor:
    """Process files in parallel with rate limiting and progress tracking"""
    
    def __init__(self, max_workers: int = 5, 
                 rate_limit_calls: int = 10, 
                 rate_limit_window: float = 60.0):
        """
        max_workers: Maximum number of concurrent tasks
        rate_limit_calls: Maximum API calls per time window
        rate_limit_window: Time window for rate limiting in seconds
        """
        self.max_workers = max_workers
        self.rate_limiter = RateLimiter(rate_limit_calls, rate_limit_window)
        self.results = {}
        self.progress = {"completed": 0, "total": 0, "failed": 0}
        self.lock = threading.Lock()
    
    async def process_file_async(self, file_path: str, 
                                  process_func: Callable, 
                                  *args, **kwargs) -> Any:
        """
        Process a single file with rate limiting
        """
        # Wait for rate limit
        await self.rate_limiter.wait_if_needed()
        
        # Execute in thread pool (since process_func is sync)
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, 
                lambda: process_func(file_path, *args, **kwargs)
            )
            
            with self.lock:
                self.progress["completed"] += 1
                if not result.success:
                    self.progress["failed"] += 1
            
            return result
            
        except Exception as e:
            with self.lock:
                self.progress["completed"] += 1
                self.progress["failed"] += 1
            
            # Return a failed result
            from report_generator import FileUpgradeResult
            return FileUpgradeResult(
                file_path=file_path,
                success=False,
                attempts=0,
                api_changes=[],
                error=f"Processing error: {str(e)}"
            )
    
    async def process_batch(self, files: List[str], 
                           process_func: Callable,
                           *args, **kwargs) -> Dict[str, Any]:
        """
        Process a batch of files in parallel
        """
        self.progress["total"] = len(files)
        self.progress["completed"] = 0
        self.progress["failed"] = 0
        
        # Create tasks
        tasks = [
            self.process_file_async(file_path, process_func, *args, **kwargs)
            for file_path in files
        ]
        
        # Process with limited concurrency
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def bounded_task(task):
            async with semaphore:
                return await task
        
        bounded_tasks = [bounded_task(task) for task in tasks]
        
        # Execute all tasks
        results = await asyncio.gather(*bounded_tasks, return_exceptions=True)
        
        # Map results to file paths
        result_dict = {}
        for file_path, result in zip(files, results):
            if isinstance(result, Exception):
                from report_generator import FileUpgradeResult
                result = FileUpgradeResult(
                    file_path=file_path,
                    success=False,
                    attempts=0,
                    api_changes=[],
                    error=str(result)
                )
            result_dict[file_path] = result
        
        return result_dict
    
    def get_progress(self) -> Dict[str, int]:
        """Get current progress"""
        with self.lock:
            return self.progress.copy()
    
    def print_progress(self):
        """Print progress bar"""
        progress = self.get_progress()
        total = progress["total"]
        completed = progress["completed"]
        failed = progress["failed"]
        
        if total == 0:
            return
        
        percentage = (completed / total) * 100
        bar_length = 40
        filled = int(bar_length * completed / total)
        bar = '=' * filled + '-' * (bar_length - filled)
        
        print(f"\rProgress: [{bar}] {percentage:.1f}% ({completed}/{total}) | Failed: {failed}", end='', flush=True)


class DependencyBatchProcessor:
    """Process files in dependency-aware batches"""
    
    def __init__(self, dependency_levels: Dict[str, int], 
                 max_workers: int = 5,
                 rate_limit_calls: int = 10):
        """
        dependency_levels: Dict mapping file_path -> dependency level
        max_workers: Max concurrent tasks per level
        rate_limit_calls: API rate limit
        """
        self.dependency_levels = dependency_levels
        self.processor = ParallelProcessor(
            max_workers=max_workers,
            rate_limit_calls=rate_limit_calls
        )
    
    def group_by_level(self, files: List[str]) -> Dict[int, List[str]]:
        """Group files by dependency level"""
        levels = {}
        
        for file_path in files:
            level = self.dependency_levels.get(file_path, 0)
            if level not in levels:
                levels[level] = []
            levels[level].append(file_path)
        
        return levels
    
    async def process_by_levels(self, files: List[str], 
                                process_func: Callable,
                                *args, **kwargs) -> Dict[str, Any]:
        """
        Process files level by level (respecting dependencies)
        Within each level, process in parallel
        """
        grouped = self.group_by_level(files)
        all_results = {}
        
        max_level = max(grouped.keys()) if grouped else 0
        
        print(f"Processing {len(files)} files across {max_level + 1} dependency levels")
        
        for level in sorted(grouped.keys()):
            level_files = grouped[level]
            print(f"\nLevel {level}: {len(level_files)} files")
            
            # Process this level in parallel
            results = await self.processor.process_batch(
                level_files, 
                process_func,
                *args, **kwargs
            )
            
            all_results.update(results)
            
            # Print summary for this level
            successful = sum(1 for r in results.values() if r.success)
            print(f"\nLevel {level} complete: {successful}/{len(level_files)} successful")
        
        return all_results


def run_parallel_upgrade(files: List[str], 
                        process_func: Callable,
                        dependency_levels: Optional[Dict[str, int]] = None,
                        max_workers: int = 5,
                        rate_limit_calls: int = 10,
                        *args, **kwargs) -> Dict[str, Any]:
    """
    Convenience function to run parallel upgrade
    
    If dependency_levels provided, processes level-by-level
    Otherwise, processes all files in parallel
    """
    
    if dependency_levels:
        processor = DependencyBatchProcessor(
            dependency_levels=dependency_levels,
            max_workers=max_workers,
            rate_limit_calls=rate_limit_calls
        )
        return asyncio.run(processor.process_by_levels(files, process_func, *args, **kwargs))
    else:
        processor = ParallelProcessor(
            max_workers=max_workers,
            rate_limit_calls=rate_limit_calls
        )
        return asyncio.run(processor.process_batch(files, process_func, *args, **kwargs))