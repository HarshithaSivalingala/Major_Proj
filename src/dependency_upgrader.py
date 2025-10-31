"""
Improved Dependency Updater
Intelligently detects and updates ML dependencies
"""

import os
import re
import ast
from typing import Set, List, Dict

# Latest stable versions as of October 2025
ML_DEPENDENCIES = {
    'tensorflow': '>=2.18.0',
    'torch': '>=2.5.0',
    'torchvision': '>=0.20.0',
    'numpy': '>=2.1.0',
    'jax': '>=0.4.35',
    'jaxlib': '>=0.4.35',
    'scikit-learn': '>=1.5.2',
    'sklearn': '>=1.5.2',
    'pandas': '>=2.2.3',
    'matplotlib': '>=3.9.2',
    'seaborn': '>=0.13.2',
    'scipy': '>=1.14.1',
    'keras': '>=3.6.0',
    'transformers': '>=4.45.0',
    'opencv-python': '>=4.10.0',
    'cv2': '>=4.10.0',
    'pillow': '>=10.4.0',
    'datasets': '>=3.0.0',
    'accelerate': '>=1.0.0',
    'sentencepiece': '>=0.2.0',
    'tokenizers': '>=0.20.0',
}


class DependencyUpdater:
    """
    Intelligently detects and updates USED dependencies in requirements.txt and setup.py
    """
    
    def __init__(self, ml_deps: Dict[str, str] = None):
        self.ml_dependencies = ml_deps or ML_DEPENDENCIES
        self.updated_deps: List[str] = []
        self.detected_imports: Set[str] = set()
    
    def scan_project_imports(self, repo_path: str) -> Set[str]:
        """
        Scan all Python files to detect actual imports used
        
        Args:
            repo_path: Root path of repository
            
        Returns:
            Set of detected import names
        """
        all_imports = set()
        file_count = 0
        
        for root, dirs, files in os.walk(repo_path):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if d not in {
                '__pycache__', '.git', '.svn', 'node_modules',
                'venv', 'env', '.venv', '.tox', 'dist', 'build'
            }]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    imports = self._extract_imports_from_file(file_path)
                    all_imports.update(imports)
                    file_count += 1
        
        print(f"📦 Scanned {file_count} Python files")
        print(f"📦 Detected imports: {sorted(all_imports)}")
        
        self.detected_imports = all_imports
        return all_imports
    
    def _extract_imports_from_file(self, file_path: str) -> Set[str]:
        """
        Extract imports from a single Python file
        
        Args:
            file_path: Path to Python file
            
        Returns:
            Set of import names
        """
        imports = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        # Get top-level package name
                        imports.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    # Get top-level package name
                    imports.add(node.module.split('.')[0])
        
        except (SyntaxError, UnicodeDecodeError, OSError) as e:
            # Skip files that can't be parsed
            pass
        
        return imports
    
    def update_requirements_txt(self, repo_path: str) -> bool:
        """
        Update or create requirements.txt with detected dependencies
        
        Args:
            repo_path: Root path of repository
            
        Returns:
            True if updated, False otherwise
        """
        req_path = os.path.join(repo_path, 'requirements.txt')
        
        # Scan project for imports
        print("🔍 Scanning project for imports...")
        self.scan_project_imports(repo_path)
        
        seen_packages = set()
        updated_lines = []
        
        # Read existing requirements.txt if it exists
        if os.path.exists(req_path):
            print(f"📝 Updating existing requirements.txt")
            with open(req_path, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                line_stripped = line.strip()
                
                # Preserve comments and empty lines
                if not line_stripped or line_stripped.startswith('#'):
                    updated_lines.append(line)
                    continue
                
                # Extract package name (handle various formats)
                pkg_match = re.match(r'^([a-zA-Z0-9_-]+)', line_stripped)
                if not pkg_match:
                    updated_lines.append(line)
                    continue
                
                pkg_name = pkg_match.group(1).lower()
                seen_packages.add(pkg_name)
                
                # Update if it's an ML dependency
                if pkg_name in self.ml_dependencies:
                    new_version = self.ml_dependencies[pkg_name]
                    new_line = f"{pkg_name}{new_version}"
                    updated_lines.append(new_line + '\n')
                    self.updated_deps.append(f"{line_stripped} → {new_line}")
                    print(f"  ⬆️  {line_stripped} → {new_line}")
                else:
                    # Keep non-ML dependencies as-is
                    updated_lines.append(line)
        else:
            print(f"📄 Creating new requirements.txt")
            updated_lines.append("# Auto-generated requirements.txt\n")
            updated_lines.append("# ML/AI dependencies\n\n")
        
        # Add missing detected ML dependencies
        added_count = 0
        for imp in sorted(self.detected_imports):
            imp_lower = imp.lower()
            
            # Handle special cases (cv2 -> opencv-python)
            if imp_lower == 'cv2':
                imp_lower = 'opencv-python'
            
            if imp_lower in self.ml_dependencies and imp_lower not in seen_packages:
                new_line = f"{imp_lower}{self.ml_dependencies[imp_lower]}"
                updated_lines.append(new_line + '\n')
                self.updated_deps.append(f"Added: {new_line}")
                print(f"  ➕ Added: {new_line}")
                added_count += 1
        
        # Write updated requirements.txt
        with open(req_path, 'w') as f:
            f.writelines(updated_lines)
        
        print(f"✅ requirements.txt updated:")
        print(f"   • {len(self.updated_deps)} total changes")
        print(f"   • {added_count} new dependencies added")
        
        return True
    
    def update_setup_py(self, repo_path: str) -> bool:
        """
        Update setup.py with latest ML dependency versions
        
        Args:
            repo_path: Root path of repository
            
        Returns:
            True if updated, False if no setup.py found
        """
        setup_path = os.path.join(repo_path, 'setup.py')
        
        if not os.path.exists(setup_path):
            print("ℹ️  No setup.py found, skipping setup update")
            return False
        
        print("📝 Updating setup.py dependencies...")
        
        with open(setup_path, 'r') as f:
            content = f.read()
        
        updated_content = content
        update_count = 0
        
        for dep, version in self.ml_dependencies.items():
            # Match package in various formats: "pkg>=1.0", 'pkg>=1.0', pkg>=1.0
            pattern = rf'(["\']?){re.escape(dep)}[>=<!=]*[^"\',\]]*(["\']?)'
            replacement = rf'\1{dep}{version}\2'
            
            new_content = re.sub(pattern, replacement, updated_content, flags=re.IGNORECASE)
            
            if new_content != updated_content:
                self.updated_deps.append(f"Updated {dep} in setup.py → {version}")
                print(f"  ⬆️  {dep} → {version}")
                updated_content = new_content
                update_count += 1
        
        if updated_content != content:
            with open(setup_path, 'w') as f:
                f.write(updated_content)
            print(f"✅ setup.py updated with {update_count} dependencies")
            return True
        
        print("ℹ️  setup.py already up-to-date")
        return False
    
    def get_update_summary(self) -> Dict[str, any]:
        """
        Get summary of updates made
        
        Returns:
            Dictionary with update statistics
        """
        return {
            "total_changes": len(self.updated_deps),
            "detected_imports": len(self.detected_imports),
            "changes": self.updated_deps,
            "imports": sorted(self.detected_imports)
        }