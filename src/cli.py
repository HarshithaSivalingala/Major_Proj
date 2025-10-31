"""
Enhanced CLI with intelligent entry point discovery
"""

import argparse
import os
import sys
import json
import tempfile
import zipfile
from dotenv import load_dotenv
from typing import Optional

# Import modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
import repo_upgrader
from entrypoint_discovery import EntryPointDiscovery, interactive_entry_point_selection

load_dotenv()


def setup_runtime_config(
    project_root: str, 
    command: Optional[str], 
    timeout: int,
    skip_install: bool,
    force_reinstall: bool
) -> Optional[str]:
    """Create temporary runtime config file and return path"""
    
    if not command:
        return None
    
    config = {
        "command": command,
        "timeout": timeout,
        "skip_install": skip_install,
        "force_reinstall": force_reinstall,
        "shell": True if any(op in command for op in ['&&', '||', '|', '>', '<']) else False,
        "max_log_chars": 6000,
        "env": {}
    }
    
    # Create temp config file
    temp_config = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    json.dump(config, temp_config, indent=2)
    temp_config.flush()
    temp_config.close()
    
    return temp_config.name


def main():
    """Command line interface for ML Repository Upgrader with entry point discovery"""
    parser = argparse.ArgumentParser(
        description="Upgrade ML repositories to use latest APIs with intelligent runtime validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode - discovers entry points automatically
  ml-upgrader old_repo/ new_repo/
  
  # Specify entry point manually
  ml-upgrader old_repo/ new_repo/ --command "python main.py"
  
  # Skip runtime validation
  ml-upgrader old_repo/ new_repo/ --no-runtime
  
  # Use specific model
  ml-upgrader tensorflow_project/ modern_tf_project/ --model openai/gpt-4
  
  # From zip file
  ml-upgrader --input old_repo.zip --output upgraded_repo.zip

The tool will:
1. Parse README files for usage examples
2. Scan for common entry files (main.py, app.py, etc.)
3. Detect test frameworks (pytest, unittest)
4. Present options for runtime validation
5. Upgrade code with validation after each file
        """
    )
    
    parser.add_argument(
        "input_path",
        nargs='?',
        help="Path to input repository or .zip file"
    )
    
    parser.add_argument(
        "output_path",
        nargs='?',
        help="Path for upgraded repository"
    )
    
    parser.add_argument(
        "--model",
        default="openai/gpt-4o-mini",
        choices=["openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4"],
        help="LLM model to use (default: openai/gpt-4o-mini)"
    )
    
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum retry attempts per file (default: 5)"
    )
    
    parser.add_argument(
        "--command", "-c",
        type=str,
        help="Runtime validation command (skips interactive discovery)"
    )
    
    parser.add_argument(
        "--no-runtime",
        action="store_true",
        help="Skip runtime validation entirely"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Runtime validation timeout in seconds (default: 120)"
    )
    
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip dependency installation before runtime validation"
    )
    
    parser.add_argument(
        "--force-reinstall",
        action="store_true",
        help="Force reinstall all dependencies"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Non-interactive mode (use first discovered entry point)"
    )
    
    args = parser.parse_args()
    
    # Validate required arguments
    if not args.input_path or not args.output_path:
        parser.print_help()
        sys.exit(1)
    
    # Check API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("❌ Error: OPENROUTER_API_KEY environment variable not set")
        print("Set it with: export OPENROUTER_API_KEY='your-key'")
        print("Or create a .env file with: OPENROUTER_API_KEY=your-key")
        sys.exit(1)
    
    # Validate input path
    if not os.path.exists(args.input_path):
        print(f"❌ Error: Input path '{args.input_path}' does not exist")
        sys.exit(1)
    
    # Handle .zip files
    temp_dir = None
    if args.input_path.endswith('.zip'):
        print("📦 Extracting .zip file...")
        temp_dir = tempfile.mkdtemp()
        extract_path = os.path.join(temp_dir, "extracted")
        
        try:
            with zipfile.ZipFile(args.input_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            args.input_path = extract_path
            print(f"✅ Extracted to: {extract_path}")
        except Exception as e:
            print(f"❌ Failed to extract zip: {e}")
            sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"🔄 ML Repository Upgrader")
    print(f"{'='*60}")
    print(f"📂 Input:  {args.input_path}")
    print(f"📂 Output: {args.output_path}")
    print(f"🤖 Model:  {args.model}")
    print(f"{'='*60}\n")
    
    # Entry point discovery and selection
    runtime_command = None
    
    if args.no_runtime:
        print("⏭️  Runtime validation disabled by --no-runtime flag\n")
    elif args.command:
        print(f"✓ Using provided runtime command: {args.command}\n")
        runtime_command = args.command
    else:
        # Interactive or automatic discovery
        if args.non_interactive:
            print("🔍 Discovering entry points (non-interactive mode)...\n")
            discovery = EntryPointDiscovery(args.input_path)
            entries = discovery.discover_all()
            
            if entries:
                runtime_command = entries[0].command
                print(f"✓ Auto-selected: {runtime_command}")
                print(f"  Confidence: {entries[0].confidence * 100:.0f}%")
                print(f"  Description: {entries[0].description}\n")
            else:
                print("⚠️  No entry points discovered, skipping runtime validation\n")
        else:
            # Interactive selection
            runtime_command = interactive_entry_point_selection(args.input_path)
            print()  # Newline after selection
    
    # Setup runtime configuration
    runtime_config_path = None
    previous_config_env = os.getenv("ML_UPGRADER_RUNTIME_CONFIG")
    
    try:
        # Create runtime config if needed
        if runtime_command:
            runtime_config_path = setup_runtime_config(
                args.input_path,
                runtime_command,
                args.timeout,
                args.skip_install,
                args.force_reinstall
            )
            os.environ["ML_UPGRADER_RUNTIME_CONFIG"] = runtime_config_path
            
            print(f"🎯 Runtime Validation Configured:")
            print(f"   Command: {runtime_command}")
            print(f"   Timeout: {args.timeout}s")
            print(f"   Skip install: {args.skip_install}")
            print(f"   Force reinstall: {args.force_reinstall}")
            print()
        
        # Set global configuration
        os.environ["ML_UPGRADER_MODEL"] = args.model
        os.environ["ML_UPGRADER_MAX_RETRIES"] = str(args.max_retries)
        
        print("🚀 Starting upgrade process...\n")
        
        # Run the upgrade
        report_path = repo_upgrader.upgrade_repo(args.input_path, args.output_path)
        
        print(f"\n{'='*60}")
        print("✅ Upgrade completed successfully!")
        print(f"{'='*60}")
        print(f"📄 Report: {report_path}")
        print(f"📂 Upgraded repository: {args.output_path}")
        
        # Show summary from report
        if os.path.exists(report_path):
            with open(report_path, 'r') as f:
                lines = f.readlines()
                for line in lines[:15]:  # Show first few lines
                    if '**' in line or '#' in line:
                        print(line.rstrip())
        
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ Upgrade failed: {str(e)}")
        print(f"{'='*60}\n")
        
        if args.verbose:
            import traceback
            print("Full traceback:")
            traceback.print_exc()
        
        sys.exit(1)
    
    finally:
        # Cleanup
        if runtime_config_path and os.path.exists(runtime_config_path):
            os.unlink(runtime_config_path)
        
        # Restore previous config env
        if previous_config_env is not None:
            os.environ["ML_UPGRADER_RUNTIME_CONFIG"] = previous_config_env
        elif "ML_UPGRADER_RUNTIME_CONFIG" in os.environ:
            del os.environ["ML_UPGRADER_RUNTIME_CONFIG"]
        
        # Cleanup temp directory if created
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()