import ast
from typing import List, Dict

class CodeChunker:
    """Intelligently split large Python files into manageable chunks"""
    
    def __init__(self, max_lines: int = 300):
        self.max_lines = max_lines
    
    def chunk_by_functions(self, code: str, filepath: str) -> List[Dict]:
        """
        Split code into chunks by top-level functions/classes
        
        Returns list of dicts with:
        - type: 'function', 'class', 'partial', or 'full'
        - name: function/class name (if applicable)
        - code: the actual code
        - start_line, end_line: line numbers
        - imports: import statements for context
        """
        try:
            tree = ast.parse(code)
            chunks = []
            lines = code.split('\n')
            
            # Extract all imports (needed for context in each chunk)
            imports = self._extract_imports(tree, lines)
            
            # Find top-level functions and classes
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    start = node.lineno - 1
                    end = node.end_lineno if node.end_lineno else len(lines)
                    
                    chunk_code = '\n'.join(lines[start:end])
                    
                    # If chunk itself is too large, mark for line-based splitting
                    if end - start > self.max_lines:
                        sub_chunks = self._split_large_chunk(chunk_code, start, imports)
                        chunks.extend(sub_chunks)
                    else:
                        chunks.append({
                            'type': 'function' if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else 'class',
                            'name': node.name,
                            'code': chunk_code,
                            'start_line': start,
                            'end_line': end,
                            'imports': imports
                        })
            
            # If no functions/classes found, return whole file
            if not chunks:
                return [{
                    'type': 'full',
                    'name': 'entire_file',
                    'code': code,
                    'start_line': 0,
                    'end_line': len(lines),
                    'imports': ''
                }]
            
            return chunks
            
        except SyntaxError:
            # If parsing fails, fall back to line-based chunking
            print(f"  ⚠️ Syntax error in {filepath}, using line-based chunking")
            return self._chunk_by_lines(code)
    
    def _extract_imports(self, tree: ast.AST, lines: List[str]) -> str:
        """Extract all import statements from the code"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if hasattr(node, 'lineno') and node.lineno <= len(lines):
                    imports.append(lines[node.lineno - 1])
            elif isinstance(node, ast.ImportFrom):
                if hasattr(node, 'lineno') and node.lineno <= len(lines):
                    imports.append(lines[node.lineno - 1])
        return '\n'.join(imports)
    
    def _split_large_chunk(self, chunk_code: str, start_line: int, imports: str) -> List[Dict]:
        """Split a very large function/class into smaller pieces"""
        lines = chunk_code.split('\n')
        sub_chunks = []
        
        for i in range(0, len(lines), self.max_lines):
            sub_code = '\n'.join(lines[i:i + self.max_lines])
            sub_chunks.append({
                'type': 'partial',
                'name': f'partial_{start_line + i}',
                'code': sub_code,
                'start_line': start_line + i,
                'end_line': start_line + min(i + self.max_lines, len(lines)),
                'imports': imports
            })
        
        return sub_chunks
    
    def _chunk_by_lines(self, code: str) -> List[Dict]:
        """Fallback: split code by line count when AST parsing fails"""
        lines = code.split('\n')
        chunks = []
        
        for i in range(0, len(lines), self.max_lines):
            chunk_lines = lines[i:i + self.max_lines]
            chunk_code = '\n'.join(chunk_lines)
            
            chunks.append({
                'type': 'partial',
                'name': f'lines_{i}_{i + len(chunk_lines)}',
                'code': chunk_code,
                'start_line': i,
                'end_line': i + len(chunk_lines),
                'imports': ''  # Can't reliably extract imports without parsing
            })
        
        return chunks