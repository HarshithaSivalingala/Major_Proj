"""
Enhanced Streamlit UI with intelligent entry point discovery
"""

import streamlit as st
import zipfile
import os
import shutil
import tempfile
import sys
import json
from dotenv import load_dotenv

# Import the entry point discovery
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
import repo_upgrader
from entrypoint_discovery import EntryPointDiscovery, EntryPoint

load_dotenv()


def display_discovered_entries(entries: list[EntryPoint]) -> str:
    """Display discovered entry points in Streamlit and get user selection"""
    
    if not entries:
        st.warning("⚠️ No entry points discovered automatically.")
        manual_command = st.text_input(
            "Enter a custom runtime command:",
            placeholder="python main.py",
            help="Enter the command to run after upgrade for validation"
        )
        return manual_command
    
    st.subheader("🔍 Discovered Entry Points")
    st.markdown("Select a command to run for runtime validation after upgrade:")
    
    # Create a formatted display
    options = []
    for entry in entries[:10]:  # Show top 10
        confidence_pct = int(entry.confidence * 100)
        label = f"{entry.command} ({confidence_pct}% confidence)"
        options.append(label)
    
    # Add custom option
    options.append("🔧 Enter custom command")
    options.append("⏭️  Skip runtime validation")
    
    # Show entries in an expander with details
    with st.expander("📋 View all discovered entry points", expanded=True):
        for i, entry in enumerate(entries[:10], 1):
            confidence_bar = "🟩" * int(entry.confidence * 10) + "⬜" * (10 - int(entry.confidence * 10))
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{i}. `{entry.command}`**")
                st.caption(f"{entry.description}")
            with col2:
                st.markdown(f"{confidence_bar}")
                st.caption(f"Type: {entry.type}")
    
    # Selection dropdown
    selected = st.selectbox(
        "Choose an entry point:",
        options,
        help="The selected command will run after each file upgrade to validate it works"
    )
    
    # Handle selection
    if selected == "⏭️  Skip runtime validation":
        return None
    elif selected == "🔧 Enter custom command":
        custom_command = st.text_input(
            "Enter custom command:",
            placeholder="python train.py --epochs 1",
            help="Full command to execute for validation"
        )
        return custom_command
    else:
        # Extract command from label (remove confidence percentage)
        command = selected.split(" (")[0]
        return command


def main():
    st.set_page_config(
        page_title="ML Repo Upgrader", 
        page_icon="🔄", 
        layout="wide"
    )
    
    st.title("🔄 ML Repository Upgrader")
    st.markdown("""
    **Automatically upgrade repositories to use the latest APIs for:**
    - TensorFlow (1.x → 2.x)
    - PyTorch (legacy → modern)
    - NumPy (deprecated functions)
    - JAX (API updates)
    """)
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        existing_api_key = os.getenv("OPENROUTER_API_KEY", "")
        api_key_input = st.text_input(
            "OpenRouter API Key (optional)",
            type="password",
            help="Leave blank to use the key from your .env file.",
        )

        if api_key_input:
            os.environ["OPENROUTER_API_KEY"] = api_key_input
            st.success("✅ API key set for this session")
        elif existing_api_key:
            st.info("Using OPENROUTER_API_KEY from environment.")
        else:
            st.warning("⚠️ Provide an OpenRouter key via .env or enter it here before running an upgrade.")

        model_options = ["openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4"]
        model = st.selectbox(
            "Model",
            model_options,
            index=0,
            help="Choose the OpenRouter model; defaults to openai/gpt-4o-mini.",
        )
        
        # Advanced settings
        with st.expander("Advanced Settings"):
            max_retries = st.slider("Max retries per file", 1, 10, 5)
            os.environ["ML_UPGRADER_MAX_RETRIES"] = str(max_retries)
            
            show_progress = st.checkbox("Show detailed progress", True)
            
            # Runtime validation timeout
            runtime_timeout = st.number_input(
                "Runtime timeout (seconds)",
                min_value=10,
                max_value=600,
                value=120,
                step=10,
                help="Maximum time to wait for runtime validation"
            )
    
    # Main interface
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📁 Upload Repository")
        
        uploaded_file = st.file_uploader(
            "Upload repository (.zip)", 
            type=["zip"],
            help="Upload a .zip file containing your ML repository"
        )
        
        if uploaded_file and not os.getenv("OPENROUTER_API_KEY"):
            st.error("❌ Please set an OpenRouter API key in the sidebar or .env before running an upgrade.")
            return

        if uploaded_file and os.getenv("OPENROUTER_API_KEY"):
            # Create temp directories
            temp_dir = tempfile.mkdtemp()
            old_repo_path = os.path.join(temp_dir, "old_repo")
            new_repo_path = os.path.join(temp_dir, "new_repo")
            
            try:
                # Extract uploaded zip
                zip_path = os.path.join(temp_dir, "uploaded.zip")
                with open(zip_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(old_repo_path)
                
                st.success("✅ Repository uploaded and extracted")
                
                # Show repository structure
                st.subheader("📂 Repository Structure")
                python_files = []
                for root, dirs, files in os.walk(old_repo_path):
                    for file in files:
                        if file.endswith('.py'):
                            rel_path = os.path.relpath(os.path.join(root, file), old_repo_path)
                            python_files.append(rel_path)
                
                st.write(f"Found **{len(python_files)}** Python files:")
                with st.expander("View files"):
                    for file in python_files[:10]:
                        st.text(f"📄 {file}")
                    if len(python_files) > 10:
                        st.text(f"... and {len(python_files) - 10} more files")
                
                # **NEW: Entry Point Discovery**
                st.divider()
                st.subheader("🎯 Runtime Validation Setup")
                
                with st.spinner("🔍 Discovering entry points..."):
                    discovery = EntryPointDiscovery(old_repo_path)
                    discovered_entries = discovery.discover_all()
                
                # Get user's choice
                selected_command = display_discovered_entries(discovered_entries)
                
                # Show what will happen
                if selected_command:
                    st.info(f"✓ Will run `{selected_command}` after each upgrade to validate")
                else:
                    st.info("⏭️  Runtime validation disabled")
                
                # Upgrade button
                if st.button("🚀 Start Upgrade", type="primary", use_container_width=True):
                    
                    # Build runtime configuration
                    runtime_config_payload = None
                    if selected_command:
                        # Parse command (could be string or need to be split)
                        runtime_config_payload = {
                            "command": selected_command,
                            "timeout": runtime_timeout,
                            "skip_install": False,
                            "force_reinstall": False,
                            "shell": True if any(op in selected_command for op in ['&&', '||', '|', '>', '<']) else False,
                            "max_log_chars": 6000,
                            "env": {},
                        }
                    
                    with st.spinner("🔄 Upgrading repository... This may take a few minutes."):
                        
                        # Progress tracking
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Start upgrade
                        status_text.text("📦 Updating dependencies...")
                        progress_bar.progress(10)
                        
                        try:
                            # Set model
                            os.environ["ML_UPGRADER_MODEL"] = model

                            # Write runtime config if provided
                            runtime_config_path = None
                            previous_runtime_config_env = os.getenv("ML_UPGRADER_RUNTIME_CONFIG")
                            try:
                                if runtime_config_payload is not None:
                                    runtime_temp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json")
                                    json.dump(runtime_config_payload, runtime_temp, indent=2)
                                    runtime_temp.flush()
                                    runtime_temp.close()
                                    runtime_config_path = runtime_temp.name
                                    os.environ["ML_UPGRADER_RUNTIME_CONFIG"] = runtime_config_path

                                status_text.text("🔄 Upgrading Python files...")
                                progress_bar.progress(30)
                                
                                report_path = repo_upgrader.upgrade_repo(old_repo_path, new_repo_path)
                                
                            finally:
                                if runtime_config_path and os.path.exists(runtime_config_path):
                                    os.unlink(runtime_config_path)
                                if previous_runtime_config_env is not None:
                                    os.environ["ML_UPGRADER_RUNTIME_CONFIG"] = previous_runtime_config_env
                                elif runtime_config_payload is not None:
                                    os.environ.pop("ML_UPGRADER_RUNTIME_CONFIG", None)

                            progress_bar.progress(90)
                            
                            status_text.text("📄 Generating report...")
                            
                            # Create downloadable zip
                            output_zip = os.path.join(temp_dir, "upgraded_repo.zip")
                            shutil.make_archive(output_zip[:-4], 'zip', new_repo_path)
                            
                            progress_bar.progress(100)
                            status_text.text("✅ Upgrade complete!")
                            
                            st.success("🎉 Repository upgraded successfully!")
                            
                        except Exception as e:
                            st.error(f"❌ Upgrade failed: {str(e)}")
                            import traceback
                            with st.expander("🐛 Debug info"):
                                st.code(traceback.format_exc())
                            return
                    
                    # Results section
                    with col2:
                        st.subheader("📊 Results")
                        
                        # Show upgrade report
                        if os.path.exists(report_path):
                            with open(report_path, 'r') as f:
                                report_content = f.read()
                            
                            # Extract summary stats
                            if "**Successful:**" in report_content:
                                lines = report_content.split('\n')
                                success_count = "0"
                                failed_count = "0"
                                for line in lines:
                                    if "**Successful:**" in line:
                                        success_count = line.split('**Successful:** ')[1].strip()
                                    if "**Failed:**" in line:
                                        failed_count = line.split('**Failed:** ')[1].strip()
                                
                                col_s, col_f = st.columns(2)
                                with col_s:
                                    st.metric("✅ Successfully Upgraded", success_count)
                                with col_f:
                                    st.metric("❌ Failed", failed_count)
                            
                            # Show report preview
                            st.subheader("📄 Upgrade Report Preview")
                            with st.expander("View Full Report"):
                                st.markdown(report_content)
                        
                        # Download buttons
                        st.subheader("📥 Downloads")
                        
                        # Download upgraded repository
                        if os.path.exists(output_zip):
                            with open(output_zip, "rb") as f:
                                st.download_button(
                                    "📦 Download Upgraded Repository",
                                    f.read(),
                                    file_name="upgraded_repo.zip",
                                    mime="application/zip",
                                    use_container_width=True
                                )
                        
                        # Download report only
                        if os.path.exists(report_path):
                            with open(report_path, "r") as f:
                                st.download_button(
                                    "📄 Download Upgrade Report",
                                    f.read(),
                                    file_name="UPGRADE_REPORT.md",
                                    mime="text/markdown",
                                    use_container_width=True
                                )
            
            except Exception as e:
                st.error(f"Error processing upload: {str(e)}")
                import traceback
                with st.expander("🐛 Debug info"):
                    st.code(traceback.format_exc())
            
            finally:
                # Cleanup
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)

    # Footer
    st.markdown("---")
    st.markdown("""
    **How it works:**
    1. Upload your legacy ML repository as a .zip file
    2. The tool discovers entry points from README and common files
    3. Select a command to validate upgrades (or skip validation)
    4. Automatically upgrades code to latest ML library APIs
    5. Download the upgraded repository with a detailed report
    
    **Supported Libraries:** TensorFlow, PyTorch, NumPy, JAX, scikit-learn, and more
    """)

if __name__ == "__main__":
    main()