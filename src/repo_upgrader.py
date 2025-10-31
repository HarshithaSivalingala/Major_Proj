import os
import shutil
import agentic_upgrader
import dependency_upgrader
import report_generator
from cache_manager import CacheManager
from dependency_analyzer import DependencyAnalyzer
from parallel_processor import run_parallel_upgrade
from typing import List

def upgrade_repo(old_repo: str, new_repo: str, 
                use_cache: bool = True, 
                respect_dependencies: bool = True,
                parallel: bool = True,
                max_workers: int = 5) -> str:
    """
    Upgrade entire repository with comprehensive reporting and caching
    Returns path to generated report
    """
    
    previous_project_root = os.getenv("ML_UPGRADER_PROJECT_ROOT")
    os.environ["ML_UPGRADER_PROJECT_ROOT"] = new_repo

    try:
        # Initialize components
        report_gen = report_generator.UpgradeReportGenerator()
        dep_updater = dependency_upgrader.DependencyUpdater()
        
        # Setup output directory
        if os.path.exists(new_repo):
            shutil.rmtree(new_repo)
        shutil.copytree(old_repo, new_repo)
        
        # Initialize cache
        cache = CacheManager(new_repo) if use_cache else None
        
        if cache:
            stats = cache.get_stats()
            if stats["total_cached"] > 0:
                print(f"Found cache: {stats['successful']} successful, {stats['failed']} failed")
        
        print(f"Starting repo upgrade: {old_repo} -> {new_repo}")
        
        # Update dependencies
        print("Updating dependencies...")
        dep_updater.update_requirements_txt(new_repo)
        dep_updater.update_setup_py(new_repo)
        report_gen.add_dependency_changes(dep_updater.updated_deps)
        
        # Collect Python files
        python_files = []
        for root, _, files in os.walk(new_repo):
            # Skip cache directory
            if cache and cache.cache_dir in root:
                continue
            
            for f in files:
                if f.endswith(".py"):
                    file_path = os.path.join(root, f)
                    
                    # Skip metadata files
                    if '__pycache__' in file_path or '.pyc' in file_path:
                        continue
                    if os.path.basename(file_path).startswith('._'):
                        continue
                    if '__MACOSX' in file_path:
                        continue
                    
                    python_files.append(file_path)
        
        print(f"Found {len(python_files)} Python files to upgrade")
        
        # Filter cached files
        files_to_process = []
        skipped_cached = 0
        
        for file_path in python_files:
            if cache and cache.is_file_cached(file_path):
                if cache.restore_from_cache(file_path, file_path):
                    skipped_cached += 1
                    # Add cached result to report
                    cached_result = cache.get_cached_result(file_path)
                    if cached_result:
                        result = report_generator.FileUpgradeResult(
                            file_path=file_path,
                            success=True,
                            attempts=cached_result.get("attempts", 0),
                            api_changes=cached_result.get("api_changes", []),
                            error=None
                        )
                        report_gen.add_file_result(result)
                    continue
            
            files_to_process.append(file_path)
        
        if skipped_cached > 0:
            print(f"Restored {skipped_cached} files from cache")
        
        if not files_to_process:
            print("All files already cached, nothing to process")
        else:
            print(f"Processing {len(files_to_process)} files...")
            
            # Analyze dependencies if needed
            dependency_levels = None
            if respect_dependencies and len(files_to_process) > 1:
                analyzer = DependencyAnalyzer(new_repo)
                dep_stats = analyzer.analyze_repository(files_to_process)
                print(f"Dependency analysis: {dep_stats['files_with_deps']} files have dependencies")
                dependency_levels = analyzer.get_dependency_levels()
            
            # Create wrapper function for parallel processing
            def process_with_cache(file_path: str, output_path: str):
                result = agentic_upgrader.upgrade_file(file_path, output_path)
                
                # Cache result
                if cache:
                    if result.success:
                        with open(file_path, 'r') as f:
                            upgraded_code = f.read()
                        cache.cache_result(file_path, result, upgraded_code)
                    else:
                        cache.cache_result(file_path, result)
                
                return result
            
            # Process files
            if parallel and len(files_to_process) > 1:
                print(f"Using parallel processing with {max_workers} workers")
                
                results = run_parallel_upgrade(
                    files_to_process,
                    process_with_cache,
                    dependency_levels=dependency_levels if respect_dependencies else None,
                    max_workers=max_workers,
                    rate_limit_calls=int(os.getenv("ML_UPGRADER_RATE_LIMIT", "10"))
                )
                
                # Add results to report
                for file_path, result in results.items():
                    report_gen.add_file_result(result)
            
            else:
                # Sequential processing (fallback)
                print("Using sequential processing")
                for i, file_path in enumerate(files_to_process, 1):
                    rel_path = os.path.relpath(file_path, new_repo)
                    print(f"[{i}/{len(files_to_process)}] Processing: {rel_path}")
                    
                    try:
                        result = process_with_cache(file_path, file_path)
                        report_gen.add_file_result(result)
                    except Exception as e:
                        print(f"Error: {e}")
                        result = report_generator.FileUpgradeResult(
                            file_path=file_path,
                            success=False,
                            attempts=0,
                            api_changes=[],
                            error=str(e)
                        )
                        report_gen.add_file_result(result)
        
        # Generate report
        report_path = os.path.join(new_repo, "UPGRADE_REPORT.md")
        report_gen.generate_report(report_path)
        
        successful = len([r for r in report_gen.results if r.success])
        total = len(report_gen.results)
        
        print("\n" + "="*60)
        print("Upgrade complete!")
        print(f"Results: {successful}/{total} files upgraded successfully")
        if skipped_cached > 0:
            print(f"Cache: {skipped_cached} files restored from cache")
        print(f"Report: {report_path}")
        print("="*60)
        
        return report_path
        
    finally:
        if previous_project_root is None:
            os.environ.pop("ML_UPGRADER_PROJECT_ROOT", None)
        else:
            os.environ["ML_UPGRADER_PROJECT_ROOT"] = previous_project_root