"""
Entry Point Discovery Module
Intelligently parses README files to discover and suggest entry points for runtime validation
"""

import os
import re
from typing import List, Dict, Optional, Set
from dataclasses import dataclass


@dataclass
class EntryPoint:
    """Discovered entry point with metadata"""
    command: str
    description: str
    confidence: float  # 0.0 to 1.0
    source_line: int
    context: str
    type: str  # 'python', 'pytest', 'shell', 'jupyter'


class EntryPointDiscovery:
    """Discover runnable entry points from README and project structure"""
    
    # Patterns for finding commands in README
    COMMAND_PATTERNS = [
        # Python execution patterns
        (r'python\s+([a-zA-Z0-9_/.-]+\.py)(?:\s+(.*))?', 'python', 0.9),
        (r'python3\s+([a-zA-Z0-9_/.-]+\.py)(?:\s+(.*))?', 'python', 0.9),
        (r'(?:^|\s)\.\/([a-zA-Z0-9_/.-]+\.py)(?:\s+(.*))?', 'python', 0.8),
        
        # Pytest patterns
        (r'pytest(?:\s+([a-zA-Z0-9_/.-]*))?', 'pytest', 0.85),
        (r'py\.test(?:\s+([a-zA-Z0-9_/.-]*))?', 'pytest', 0.85),
        
        # Python module execution
        (r'python\s+-m\s+([a-zA-Z0-9_.-]+)(?:\s+(.*))?', 'python', 0.9),
        
        # Jupyter patterns
        (r'jupyter\s+notebook(?:\s+([a-zA-Z0-9_/.-]+\.ipynb))?', 'jupyter', 0.7),
        
        # Shell script patterns
        (r'(?:bash|sh)\s+([a-zA-Z0-9_/.-]+\.sh)(?:\s+(.*))?', 'shell', 0.7),
        (r'\.\/([a-zA-Z0-9_/.-]+\.sh)(?:\s+(.*))?', 'shell', 0.7),
    ]
    
    # Keywords that indicate runnable examples
    EXAMPLE_KEYWORDS = [
        'usage', 'example', 'quickstart', 'getting started',
        'run', 'execute', 'demo', 'tutorial', 'how to use'
    ]
    
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.discovered_entries: List[EntryPoint] = []
    
    def discover_all(self) -> List[EntryPoint]:
        """Main discovery method - finds all possible entry points"""
        self.discovered_entries = []
        
        # 1. Parse README files
        readme_entries = self._parse_readme_files()
        self.discovered_entries.extend(readme_entries)
        
        # 2. Scan for common entry point files
        file_entries = self._scan_common_files()
        self.discovered_entries.extend(file_entries)
        
        # 3. Detect test frameworks
        test_entries = self._detect_test_framework()
        self.discovered_entries.extend(test_entries)
        
        # 4. Look for setup.py entry points
        setup_entries = self._parse_setup_py()
        self.discovered_entries.extend(setup_entries)
        
        # Remove duplicates and sort by confidence
        self.discovered_entries = self._deduplicate_entries(self.discovered_entries)
        self.discovered_entries.sort(key=lambda e: e.confidence, reverse=True)
        
        return self.discovered_entries
    
    def _parse_readme_files(self) -> List[EntryPoint]:
        """Parse README files for command examples"""
        entries = []
        readme_paths = self._find_readme_files()
        
        for readme_path in readme_paths:
            try:
                with open(readme_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract commands from code blocks
                entries.extend(self._extract_from_code_blocks(content, readme_path))
                
                # Extract commands from inline code
                entries.extend(self._extract_from_inline_code(content, readme_path))
                
            except Exception as e:
                print(f"⚠️ Could not parse {readme_path}: {e}")
        
        return entries
    
    def _find_readme_files(self) -> List[str]:
        """Find all README files in the project"""
        readme_files = []
        readme_names = ['README.md', 'README.rst', 'README.txt', 'README', 'readme.md']
        
        for root, dirs, files in os.walk(self.project_root):
            # Skip hidden and common non-source directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules']]
            
            for file in files:
                if file in readme_names or file.lower().startswith('readme'):
                    readme_files.append(os.path.join(root, file))
        
        return readme_files
    
    def _extract_from_code_blocks(self, content: str, source_file: str) -> List[EntryPoint]:
        """Extract commands from markdown/rst code blocks"""
        entries = []
        
        # Find all code blocks (markdown style)
        code_blocks = re.finditer(r'```(?:bash|sh|python|shell)?\n(.*?)```', content, re.DOTALL)
        
        for match in code_blocks:
            block_content = match.group(1)
            lines = block_content.split('\n')
            
            for line_num, line in enumerate(lines):
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Check against patterns
                for pattern, cmd_type, base_confidence in self.COMMAND_PATTERNS:
                    if re.search(pattern, line):
                        # Check if line is in an example section
                        context = self._get_context(content, match.start())
                        confidence = base_confidence
                        
                        if any(keyword in context.lower() for keyword in self.EXAMPLE_KEYWORDS):
                            confidence += 0.05
                        
                        entries.append(EntryPoint(
                            command=line,
                            description=self._extract_description(content, match.start()),
                            confidence=min(confidence, 1.0),
                            source_line=line_num,
                            context=context,
                            type=cmd_type
                        ))
        
        return entries
    
    def _extract_from_inline_code(self, content: str, source_file: str) -> List[EntryPoint]:
        """Extract commands from inline code (backticks)"""
        entries = []
        
        # Find inline code
        inline_code = re.finditer(r'`([^`]+)`', content)
        
        for match in inline_code:
            command = match.group(1).strip()
            
            # Check against patterns
            for pattern, cmd_type, base_confidence in self.COMMAND_PATTERNS:
                if re.search(pattern, command):
                    context = self._get_context(content, match.start())
                    
                    # Lower confidence for inline code
                    confidence = base_confidence - 0.2
                    
                    entries.append(EntryPoint(
                        command=command,
                        description=self._extract_description(content, match.start()),
                        confidence=max(confidence, 0.0),
                        source_line=0,
                        context=context,
                        type=cmd_type
                    ))
        
        return entries
    
    def _scan_common_files(self) -> List[EntryPoint]:
        """Scan for common entry point files in project root"""
        entries = []
        common_files = [
            ('main.py', 0.85, 'Standard main entry point'),
            ('app.py', 0.8, 'Application entry point'),
            ('run.py', 0.8, 'Run script'),
            ('train.py', 0.75, 'ML training script'),
            ('test.py', 0.7, 'Test script'),
            ('demo.py', 0.7, 'Demo script'),
            ('example.py', 0.65, 'Example script'),
        ]
        
        for filename, confidence, description in common_files:
            file_path = os.path.join(self.project_root, filename)
            if os.path.exists(file_path):
                entries.append(EntryPoint(
                    command=f"python {filename}",
                    description=description,
                    confidence=confidence,
                    source_line=0,
                    context=f"Found common entry file: {filename}",
                    type='python'
                ))
        
        return entries
    
    def _detect_test_framework(self) -> List[EntryPoint]:
        """Detect and suggest test framework commands"""
        entries = []
        
        # Check for pytest
        if self._has_pytest():
            entries.append(EntryPoint(
                command="pytest",
                description="Run pytest test suite",
                confidence=0.9,
                source_line=0,
                context="Detected pytest configuration",
                type='pytest'
            ))
        
        # Check for unittest
        if self._has_unittest():
            entries.append(EntryPoint(
                command="python -m unittest discover",
                description="Run unittest test suite",
                confidence=0.85,
                source_line=0,
                context="Detected unittest tests",
                type='python'
            ))
        
        return entries
    
    def _parse_setup_py(self) -> List[EntryPoint]:
        """Parse setup.py for console_scripts entry points"""
        entries = []
        setup_path = os.path.join(self.project_root, 'setup.py')
        
        if not os.path.exists(setup_path):
            return entries
        
        try:
            with open(setup_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find console_scripts or entry_points
            entry_points_match = re.search(
                r'entry_points\s*=\s*\{[^}]*["\']console_scripts["\']\s*:\s*\[(.*?)\]',
                content,
                re.DOTALL
            )
            
            if entry_points_match:
                scripts = entry_points_match.group(1)
                script_lines = re.findall(r'["\']([^"\']+)["\']', scripts)
                
                for script in script_lines:
                    if '=' in script:
                        command_name = script.split('=')[0].strip()
                        entries.append(EntryPoint(
                            command=command_name,
                            description=f"Console script from setup.py: {command_name}",
                            confidence=0.95,
                            source_line=0,
                            context="Defined in setup.py entry_points",
                            type='python'
                        ))
        
        except Exception as e:
            print(f"⚠️ Could not parse setup.py: {e}")
        
        return entries
    
    def _has_pytest(self) -> bool:
        """Check if project uses pytest"""
        indicators = [
            'pytest.ini',
            'pyproject.toml',  # might have pytest config
            'setup.cfg',  # might have pytest config
            'tests',  # common test directory
        ]
        
        for indicator in indicators:
            if os.path.exists(os.path.join(self.project_root, indicator)):
                return True
        
        # Check requirements.txt
        req_path = os.path.join(self.project_root, 'requirements.txt')
        if os.path.exists(req_path):
            with open(req_path, 'r') as f:
                if 'pytest' in f.read().lower():
                    return True
        
        return False
    
    def _has_unittest(self) -> bool:
        """Check if project uses unittest"""
        # Look for test files with unittest imports
        for root, _, files in os.walk(self.project_root):
            for file in files:
                if file.startswith('test_') and file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if 'import unittest' in content or 'from unittest' in content:
                                return True
                    except:
                        pass
        
        return False
    
    def _get_context(self, content: str, position: int, context_size: int = 200) -> str:
        """Get surrounding context for a position in the content"""
        start = max(0, position - context_size)
        end = min(len(content), position + context_size)
        return content[start:end]
    
    def _extract_description(self, content: str, position: int) -> str:
        """Extract a description from surrounding text"""
        lines = content[:position].split('\n')
        
        # Look backwards for a heading or description
        for line in reversed(lines[-5:]):
            line = line.strip()
            if line and not line.startswith('```') and not line.startswith('#'):
                # Remove markdown formatting
                line = re.sub(r'[*_`]', '', line)
                if len(line) > 10 and len(line) < 100:
                    return line
        
        return "Command found in documentation"
    
    def _deduplicate_entries(self, entries: List[EntryPoint]) -> List[EntryPoint]:
        """Remove duplicate entries, keeping highest confidence"""
        seen: Dict[str, EntryPoint] = {}
        
        for entry in entries:
            key = entry.command.strip().lower()
            if key not in seen or entry.confidence > seen[key].confidence:
                seen[key] = entry
        
        return list(seen.values())
    
    def format_for_display(self, entries: List[EntryPoint], max_entries: int = 10) -> str:
        """Format entries for CLI display"""
        output = ["📋 Discovered Entry Points:\n"]
        
        for i, entry in enumerate(entries[:max_entries], 1):
            confidence_bar = "█" * int(entry.confidence * 10)
            output.append(f"{i}. [{confidence_bar:10s}] {entry.command}")
            output.append(f"   Type: {entry.type} | {entry.description}")
            output.append("")
        
        if len(entries) > max_entries:
            output.append(f"... and {len(entries) - max_entries} more entries")
        
        return "\n".join(output)


def interactive_entry_point_selection(project_root: str) -> Optional[str]:
    """Interactive CLI for selecting entry point"""
    print("🔍 Discovering entry points...\n")
    
    discovery = EntryPointDiscovery(project_root)
    entries = discovery.discover_all()
    
    if not entries:
        print("❌ No entry points discovered automatically.")
        manual = input("Enter a custom command to run (or press Enter to skip): ").strip()
        return manual if manual else None
    
    print(discovery.format_for_display(entries))
    print("\nOptions:")
    print("  1-N: Select an entry point by number")
    print("  custom: Enter a custom command")
    print("  skip: Skip runtime validation")
    
    while True:
        choice = input("\nYour choice: ").strip().lower()
        
        if choice == 'skip':
            return None
        
        if choice == 'custom':
            custom_cmd = input("Enter custom command: ").strip()
            return custom_cmd if custom_cmd else None
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(entries):
                selected = entries[idx]
                print(f"\n✅ Selected: {selected.command}")
                return selected.command
            else:
                print(f"❌ Invalid selection. Choose 1-{len(entries)}")
        except ValueError:
            print("❌ Invalid input. Enter a number, 'custom', or 'skip'")


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
    else:
        project_path = "."
    
    selected_command = interactive_entry_point_selection(project_path)
    
    if selected_command:
        print(f"\n🚀 Would run: {selected_command}")
    else:
        print("\n⏭️  Skipping runtime validation")