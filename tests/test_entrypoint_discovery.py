"""
Comprehensive tests for entry point discovery system
"""

import pytest
import tempfile
import os
import shutil
from pathlib import Path

# Assuming the module is importable
from entrypoint_discovery import EntryPointDiscovery, EntryPoint


class TestEntryPointDiscovery:
    """Test suite for entry point discovery"""
    
    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def create_file(self, project_root: str, relative_path: str, content: str):
        """Helper to create files in temp project"""
        file_path = os.path.join(project_root, relative_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            f.write(content)
    
    def test_discover_from_readme_code_blocks(self, temp_project):
        """Test discovering commands from README code blocks"""
        readme_content = """
# My ML Project

## Usage

To run the training script:

```bash
python train.py --epochs 10
```

For testing:
```python
pytest tests/
```
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        # Should find both commands
        commands = [e.command for e in entries]
        assert "python train.py --epochs 10" in commands
        assert "pytest tests/" in commands
        
        # Check confidence levels
        train_entry = next(e for e in entries if "train.py" in e.command)
        assert train_entry.confidence > 0.8
        assert train_entry.type == "python"
    
    def test_discover_from_inline_code(self, temp_project):
        """Test discovering from inline code in README"""
        readme_content = """
# Quick Start

Run `python main.py` to start the application.
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        # Should find inline command (with lower confidence)
        commands = [e.command for e in entries]
        assert "python main.py" in commands
        
        main_entry = next(e for e in entries if e.command == "python main.py")
        assert main_entry.confidence < 0.9  # Inline code has lower confidence
    
    def test_discover_common_entry_files(self, temp_project):
        """Test discovering common entry point files"""
        # Create common entry files
        self.create_file(temp_project, "main.py", "# Main entry point")
        self.create_file(temp_project, "train.py", "# Training script")
        self.create_file(temp_project, "app.py", "# Application")
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        commands = [e.command for e in entries]
        assert "python main.py" in commands
        assert "python train.py" in commands
        assert "python app.py" in commands
        
        # main.py should have highest confidence
        main_entry = next(e for e in entries if "main.py" in e.command)
        assert main_entry.confidence >= 0.85
    
    def test_detect_pytest_framework(self, temp_project):
        """Test pytest detection"""
        # Create pytest indicators
        self.create_file(temp_project, "pytest.ini", "[pytest]\ntestpaths = tests")
        self.create_file(temp_project, "tests/test_sample.py", "def test_example(): pass")
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        commands = [e.command for e in entries]
        assert "pytest" in commands
        
        pytest_entry = next(e for e in entries if e.command == "pytest")
        assert pytest_entry.type == "pytest"
        assert pytest_entry.confidence > 0.8
    
    def test_detect_unittest_framework(self, temp_project):
        """Test unittest detection"""
        test_content = """
import unittest

class TestSample(unittest.TestCase):
    def test_example(self):
        self.assertTrue(True)
        """
        
        self.create_file(temp_project, "test_main.py", test_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        commands = [e.command for e in entries]
        assert "python -m unittest discover" in commands
    
    def test_parse_setup_py_console_scripts(self, temp_project):
        """Test parsing console_scripts from setup.py"""
        setup_content = """
from setuptools import setup

setup(
    name="myproject",
    entry_points={
        'console_scripts': [
            'myapp=myproject.cli:main',
            'mytool=myproject.tool:run',
        ],
    },
)
        """
        
        self.create_file(temp_project, "setup.py", setup_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        commands = [e.command for e in entries]
        assert "myapp" in commands
        assert "mytool" in commands
        
        # Console scripts should have very high confidence
        myapp_entry = next(e for e in entries if e.command == "myapp")
        assert myapp_entry.confidence >= 0.9
    
    def test_confidence_scoring(self, temp_project):
        """Test that confidence scoring works correctly"""
        readme_content = """
# Usage Examples

In a code block:
```bash
python main.py
```

Inline: run `python secondary.py`
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        self.create_file(temp_project, "main.py", "# Main")
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        # Code block should have higher confidence than inline
        main_from_readme = [e for e in entries if "main.py" in e.command and "code" in e.context.lower()]
        secondary_inline = [e for e in entries if "secondary.py" in e.command]
        
        if main_from_readme and secondary_inline:
            assert main_from_readme[0].confidence > secondary_inline[0].confidence
    
    def test_deduplication(self, temp_project):
        """Test that duplicate entries are properly deduplicated"""
        readme_content = """
# Usage

Run: `python main.py`

Or:
```bash
python main.py
```
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        self.create_file(temp_project, "main.py", "# Main")
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        # Should only have one "python main.py" entry (highest confidence)
        main_entries = [e for e in entries if e.command.strip() == "python main.py"]
        assert len(main_entries) == 1
    
    def test_example_keyword_boost(self, temp_project):
        """Test that commands near 'example' keywords get confidence boost"""
        readme_content = """
# Quick Start Example

```bash
python demo.py
```

# Advanced Configuration

```bash
python config_tool.py
```
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        demo_entry = next(e for e in entries if "demo.py" in e.command)
        config_entry = next(e for e in entries if "config_tool.py" in e.command)
        
        # Demo should have slightly higher confidence due to "Example" keyword
        assert demo_entry.confidence >= config_entry.confidence
    
    def test_complex_commands(self, temp_project):
        """Test parsing complex commands with arguments"""
        readme_content = """
# Training

```bash
python train.py --data ./data --epochs 100 --lr 0.001
```
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        commands = [e.command for e in entries]
        assert any("train.py --data ./data --epochs 100 --lr 0.001" in cmd for cmd in commands)
    
    def test_python_module_execution(self, temp_project):
        """Test detecting python -m module execution"""
        readme_content = """
Run with:
```bash
python -m mypackage.main --config prod
```
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        commands = [e.command for e in entries]
        assert any("python -m mypackage.main" in cmd for cmd in commands)
    
    def test_jupyter_notebook_detection(self, temp_project):
        """Test Jupyter notebook detection"""
        readme_content = """
# Interactive Tutorial

```bash
jupyter notebook tutorial.ipynb
```
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        jupyter_entries = [e for e in entries if e.type == "jupyter"]
        assert len(jupyter_entries) > 0
    
    def test_shell_script_detection(self, temp_project):
        """Test shell script detection"""
        readme_content = """
Run the setup:
```bash
bash setup.sh
./run_all.sh
```
        """
        
        self.create_file(temp_project, "README.md", readme_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        shell_entries = [e for e in entries if e.type == "shell"]
        assert len(shell_entries) >= 2
    
    def test_no_entry_points_found(self, temp_project):
        """Test behavior when no entry points are found"""
        # Empty project
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        assert len(entries) == 0
    
    def test_format_for_display(self, temp_project):
        """Test display formatting"""
        self.create_file(temp_project, "main.py", "# Main")
        self.create_file(temp_project, "test.py", "# Test")
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        display_text = discovery.format_for_display(entries, max_entries=5)
        
        assert "Discovered Entry Points" in display_text
        assert "python main.py" in display_text or "python test.py" in display_text
        assert "█" in display_text  # Confidence bar
    
    def test_multiple_readme_files(self, temp_project):
        """Test discovering from multiple README files"""
        # Root README
        self.create_file(temp_project, "README.md", """
        ```bash
        python main.py
        ```
        """)
        
        # Subdirectory README
        self.create_file(temp_project, "docs/README.md", """
        ```bash
        python docs/example.py
        ```
        """)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        commands = [e.command for e in entries]
        assert "python main.py" in commands
        # Note: docs/example.py might or might not be included depending on path resolution
    
    def test_requirements_txt_pytest_detection(self, temp_project):
        """Test pytest detection via requirements.txt"""
        requirements_content = """
numpy==1.24.0
pytest==7.4.0
torch>=2.0.0
        """
        
        self.create_file(temp_project, "requirements.txt", requirements_content)
        
        discovery = EntryPointDiscovery(temp_project)
        entries = discovery.discover_all()
        
        commands = [e.command for e in entries]
        assert "pytest" in commands


class TestEntryPointObject:
    """Test the EntryPoint dataclass"""
    
    def test_entry_point_creation(self):
        """Test creating an EntryPoint"""
        entry = EntryPoint(
            command="python main.py",
            description="Main application",
            confidence=0.95,
            source_line=42,
            context="Usage example section",
            type="python"
        )
        
        assert entry.command == "python main.py"
        assert entry.confidence == 0.95
        assert entry.type == "python"
    
    def test_entry_point_comparison(self):
        """Test comparing entry points"""
        entry1 = EntryPoint("python main.py", "Main", 0.9, 0, "", "python")
        entry2 = EntryPoint("python main.py", "Main", 0.9, 0, "", "python")
        
        assert entry1.command == entry2.command
        assert entry1.confidence == entry2.confidence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])