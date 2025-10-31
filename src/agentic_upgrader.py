import os
import re
from typing import Optional
import report_generator
import llm_interface
import validator
import utils
from chunker import CodeChunker

def upgrade_file(input_path: str, output_path: str) -> report_generator.FileUpgradeResult:
    """Upgrade a single file with hybrid strategy and detailed tracking"""
    
    MAX_RETRIES = int(os.getenv("ML_UPGRADER_MAX_RETRIES", "5"))
    
    if not os.path.exists(input_path):
        return report_generator.FileUpgradeResult(
            file_path=input_path,
            success=False,
            attempts=0,
            api_changes=[],
            error="Input file not found"
        )

    skip_reason = utils.should_skip_for_upgrade(input_path)
    if skip_reason:
        print(f"Skipping {input_path}: {skip_reason}")
        return report_generator.FileUpgradeResult(
            file_path=input_path,
            success=False,
            attempts=0,
            api_changes=[],
            error=skip_reason
        )
    
    old_code = utils.read_file(input_path)
    line_count = len(old_code.split('\n'))
    
    # Pre-validation check
    try:
        precheck_valid, precheck_error = validator.validate_code(input_path)
        if not precheck_valid:
            print(f"Pre-check failed for {input_path}: {precheck_error}")
    except Exception as exc:
        precheck_error = str(exc)
    
    # HYBRID DECISION LOGIC
    if line_count < 1000:
        # Small file - direct upgrade (most efficient)
        print(f"Small file ({line_count} lines) - standard upgrade")
        return _upgrade_standard(input_path, output_path, old_code, MAX_RETRIES)
    
    elif line_count < 3000:
        # Medium file - try whole first, fallback to chunking
        print(f"Medium file ({line_count} lines) - trying standard upgrade first")
        result = _upgrade_standard(input_path, output_path, old_code, MAX_RETRIES)
        
        if not result.success and result.error and ("token" in result.error.lower() or "context_length" in result.error.lower()):
            # Token limit hit - retry with chunking
            print(f"Token limit detected, retrying with chunking...")
            return _upgrade_chunked(input_path, output_path, old_code)
        
        return result
    
    else:
        # Large file - must chunk from start
        print(f"Large file ({line_count} lines) - using chunked approach")
        return _upgrade_chunked(input_path, output_path, old_code)


def _upgrade_standard(input_path: str, output_path: str, old_code: str, MAX_RETRIES: int) -> report_generator.FileUpgradeResult:
    """Standard upgrade logic for whole file at once"""
    error = None
    current_code = old_code

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            prompt = utils.build_prompt(current_code, error)
            response = llm_interface.call_llm(prompt)
            new_code = clean_llm_response(response)

            stripped_code = new_code.strip()
            if not stripped_code:
                error = "LLM returned empty response"
                print(f"{input_path} attempt {attempt} error: {error}")
                continue

            apology_prefixes = ("i'm sorry", "im sorry", "sorry", "i cannot", "i can't")
            if stripped_code.lower().startswith(apology_prefixes) or stripped_code.startswith("# upgraded code here"):
                error = "LLM returned placeholder text instead of upgraded code"
                print(f"{input_path} attempt {attempt} error: {error}")
                continue

            utils.write_file(output_path, new_code)
            
            # Validate the new code
            is_valid, error = validator.validate_code(output_path)
            
            if is_valid:
                # Success! Generate final result
                api_changes = utils.extract_api_changes(old_code, new_code)
                diff = utils.generate_diff(old_code, new_code, os.path.basename(input_path))
                
                print(f"{input_path} upgraded successfully in {attempt} attempts")
                
                return report_generator.FileUpgradeResult(
                    file_path=input_path,
                    success=True,
                    attempts=attempt,
                    api_changes=api_changes,
                    diff=diff
                )
            
            # If validation failed, use the new code for next iteration
            current_code = new_code
            print(f"{input_path} attempt {attempt} failed: {error}")
            
        except Exception as e:
            error = str(e)
            # Check if it's a token limit error
            if "token" in error.lower() or "context_length" in error.lower() or "maximum context length" in error.lower():
                # Break early and return token error
                print(f"{input_path} token limit exceeded")
                return report_generator.FileUpgradeResult(
                    file_path=input_path,
                    success=False,
                    attempts=attempt,
                    api_changes=[],
                    error=f"Token limit exceeded: {error}"
                )
            print(f"⚠️ {input_path} attempt {attempt} error: {error}")

    # All attempts failed
    print(f"Failed to upgrade {input_path} after {MAX_RETRIES} attempts")
    
    return report_generator.FileUpgradeResult(
        file_path=input_path,
        success=False,
        attempts=MAX_RETRIES,
        api_changes=[],
        error=error or "Maximum retries exceeded"
    )


def _upgrade_chunked(input_path: str, output_path: str, old_code: str) -> report_generator.FileUpgradeResult:
    """Chunked upgrade for large files"""
    
    MAX_RETRIES = int(os.getenv("ML_UPGRADER_MAX_RETRIES_CHUNK", "3"))  # Fewer retries per chunk
    
    chunker = CodeChunker(max_lines=300)
    chunks = chunker.chunk_by_functions(old_code, input_path)
    
    print(f" Split into {len(chunks)} chunks")
    
    upgraded_chunks = []
    all_api_changes = []
    total_attempts = 0
    failed_chunks = []
    
    for i, chunk in enumerate(chunks):
        chunk_name = chunk.get('name', f"chunk-{i}")
        chunk_type = chunk.get('type', 'unknown')
        print(f"  [{i+1}/{len(chunks)}] Upgrading {chunk_type} '{chunk_name}'...")
        
        # Prepare chunk with imports for context
        chunk_code = chunk['imports'] + '\n\n' + chunk['code'] if chunk['imports'] else chunk['code']
        error = None
        
        chunk_upgraded = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                prompt = utils.build_prompt(chunk_code, error)
                response = llm_interface.call_llm(prompt)
                upgraded = clean_llm_response(response)
                
                if not upgraded.strip():
                    error = "Empty response"
                    continue
                
                apology_prefixes = ("i'm sorry", "im sorry", "sorry", "i cannot", "i can't")
                if upgraded.strip().lower().startswith(apology_prefixes):
                    error = "LLM returned placeholder text"
                    continue
                
                # Quick syntax validation
                is_valid, error = validator.validate_syntax(upgraded)
                
                if is_valid:
                    # Remove imports from upgraded chunk (we'll add them back at reassembly)
                    if chunk['imports']:
                        upgraded_no_imports = upgraded.replace(chunk['imports'], '').strip()
                        upgraded_chunks.append(upgraded_no_imports)
                    else:
                        upgraded_chunks.append(upgraded)
                    
                    # Track API changes
                    chunk_changes = utils.extract_api_changes(chunk['code'], upgraded)
                    all_api_changes.extend(chunk_changes)
                    
                    total_attempts += attempt
                    chunk_upgraded = True
                    print(f"{chunk_name} upgraded in {attempt} attempt(s)")
                    break
                    
            except Exception as e:
                error = str(e)
                print(f"    ⚠️ {chunk_name} attempt {attempt} error: {error}")
        
        if not chunk_upgraded:
            # Fallback: keep original chunk
            print(f"{chunk_name} failed after {MAX_RETRIES} attempts, keeping original")
            upgraded_chunks.append(chunk['code'])
            failed_chunks.append(chunk_name)
            total_attempts += MAX_RETRIES
    
    # Reassemble file: imports at top, then all chunks
    first_chunk = chunks[0]
    final_parts = []
    
    if first_chunk['imports']:
        final_parts.append(first_chunk['imports'])
    
    final_parts.extend(upgraded_chunks)
    final_code = '\n\n'.join(final_parts)
    
    utils.write_file(output_path, final_code)
    
    # Overall validation
    is_valid, final_error = validator.validate_code(output_path)
    
    # Consider success if valid or at least 80% chunks succeeded
    success_rate = (len(chunks) - len(failed_chunks)) / len(chunks)
    success = is_valid and success_rate >= 0.8  # 80% threshold
    
    result_error = None
    if failed_chunks:
        result_error = f"Failed chunks: {', '.join(failed_chunks)}"
    if not is_valid:
        result_error = f"{result_error}; Validation error: {final_error}" if result_error else f"Validation error: {final_error}"
    
    print(f" Chunk upgrade complete: {len(chunks) - len(failed_chunks)}/{len(chunks)} successful")
    
    return report_generator.FileUpgradeResult(
        file_path=input_path,
        success=success,
        attempts=total_attempts,
        api_changes=all_api_changes,
        error=result_error,
        diff=utils.generate_diff(old_code, final_code, os.path.basename(input_path)) if success else None
    )


def clean_llm_response(response: str) -> str:
    """Extract the upgraded Python code from LLM response (strip markdown, explanations)"""
    # Extract text inside the first ```python ... ```
    match = re.search(r"```python\s*(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Fallback: try just ``` ... ```
    match = re.search(r"```\s*(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    return response.strip()