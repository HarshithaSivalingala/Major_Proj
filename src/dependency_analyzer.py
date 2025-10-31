import os
import ast
from typing import Dict, List, Set, Tuple
from collections import defaultdict, deque

class DependencyAnalyzer:
    """Analyze and order Python files by their import dependencies"""
    
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.file_imports = {}  # file -> set of imported modules
        self.module_to_file = {}  # module name -> file path
        self.dependency_graph = defaultdict(set)  # file -> files it depends on
    
    def analyze_repository(self, python_files: List[str]) -> Dict:
        """Analyze all files and build dependency graph"""
        print("Analyzing dependencies...")
        
        # First pass: map modules to files
        for file_path in python_files:
            module_name = self._get_module_name(file_path)
            self.module_to_file[module_name] = file_path
        
        # Second pass: extract imports
        for file_path in python_files:
            imports = self._extract_imports(file_path)
            self.file_imports[file_path] = imports
        
        # Third pass: build dependency graph
        for file_path in python_files:
            imports = self.file_imports.get(file_path, set())
            for imp in imports:
                if imp in self.module_to_file:
                    dependency_file = self.module_to_file[imp]
                    if dependency_file != file_path:  # avoid self-loops
                        self.dependency_graph[file_path].add(dependency_file)
        
        return {
            'total_files': len(python_files),
            'total_dependencies': sum(len(deps) for deps in self.dependency_graph.values()),
            'files_with_deps': len([f for f in self.dependency_graph if self.dependency_graph[f]])
        }
    
    def _get_module_name(self, file_path: str) -> str:
        """Convert file path to Python module name"""
        rel_path = os.path.relpath(file_path, self.repo_path)
        module_path = rel_path.replace(os.sep, '.').replace('.py', '')
        
        # Handle __init__.py
        if module_path.endswith('.__init__'):
            module_path = module_path[:-9]
        
        return module_path
    
    def _extract_imports(self, file_path: str) -> Set[str]:
        """Extract all local imports from a Python file"""
        imports = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.level == 0:  # absolute import
                        imports.add(node.module.split('.')[0])
                    elif node.level > 0:  # relative import
                        # Handle relative imports like "from . import x" or "from .. import y"
                        current_module = self._get_module_name(file_path)
                        parts = current_module.split('.')
                        if node.level <= len(parts):
                            parent_parts = parts[:-node.level] if node.level > 0 else parts
                            if node.module:
                                imports.add('.'.join(parent_parts + [node.module.split('.')[0]]))
                            else:
                                imports.add('.'.join(parent_parts))
        
        except (SyntaxError, UnicodeDecodeError, OSError):
            pass
        
        return imports
    
    def get_upgrade_order(self) -> List[str]:
        """
        Get files in dependency order using topological sort
        Files with no dependencies come first
        """
        # Detect cycles
        cycles = self._detect_cycles()
        if cycles:
            print(f"Warning: Detected {len(cycles)} circular dependencies")
            for cycle in cycles[:3]:  # show first 3
                cycle_names = [os.path.basename(f) for f in cycle]
                print(f"  Cycle: {' -> '.join(cycle_names)}")
        
        # Topological sort with cycle handling
        in_degree = defaultdict(int)
        all_files = set(self.dependency_graph.keys())
        
        # Add files with no dependencies
        for file_path in self.file_imports.keys():
            if file_path not in all_files:
                all_files.add(file_path)
        
        # Calculate in-degrees
        for file_path in all_files:
            for dep in self.dependency_graph[file_path]:
                in_degree[dep] += 1
        
        # Start with files that have no dependencies
        queue = deque([f for f in all_files if in_degree[f] == 0])
        sorted_files = []
        
        while queue:
            file_path = queue.popleft()
            sorted_files.append(file_path)
            
            # Reduce in-degree for dependents
            for other_file in all_files:
                if file_path in self.dependency_graph[other_file]:
                    in_degree[other_file] -= 1
                    if in_degree[other_file] == 0:
                        queue.append(other_file)
        
        # Handle remaining files (part of cycles)
        remaining = all_files - set(sorted_files)
        if remaining:
            print(f"Warning: {len(remaining)} files in cycles, adding at end")
            sorted_files.extend(sorted(remaining))
        
        return sorted_files
    
    def _detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies using DFS"""
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self.dependency_graph[node]:
                if neighbor not in visited:
                    dfs(neighbor, path[:])
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
            
            rec_stack.remove(node)
        
        for file_path in self.dependency_graph.keys():
            if file_path not in visited:
                dfs(file_path, [])
        
        return cycles
    
    def get_dependency_levels(self) -> Dict[str, int]:
        """
        Assign level to each file (0 = no deps, 1 = depends on level 0, etc.)
        Useful for parallel processing within levels
        """
        levels = {}
        
        def get_level(file_path: str, visiting: Set[str]) -> int:
            if file_path in levels:
                return levels[file_path]
            
            if file_path in visiting:
                # Circular dependency, assign current max + 1
                return max(levels.values()) + 1 if levels else 0
            
            visiting.add(file_path)
            
            deps = self.dependency_graph[file_path]
            if not deps:
                level = 0
            else:
                level = max(get_level(dep, visiting.copy()) for dep in deps) + 1
            
            levels[file_path] = level
            return level
        
        for file_path in self.file_imports.keys():
            get_level(file_path, set())
        
        return levels