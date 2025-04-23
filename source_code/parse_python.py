import ast
import inspect
import os
import re
from typing import Dict, List, Optional, Tuple, Any

class ToolFunctionExtractor:
    """
    A class to extract source code and docstrings from functions decorated with @mcp.tool()
    """

    def __init__(self, file_path: str):
        """
        Initialize with the path to the Python file to analyze

        Args:
            file_path: Path to the Python file
        """
        self.file_path = file_path
        self.source_code = self._read_file()
        self.tree = ast.parse(self.source_code)

    def _read_file(self) -> str:
        """Read the content of the file"""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _get_decorator_name(self, decorator: ast.expr) -> str:
        """Extract the name of a decorator"""
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                return f"{self._get_decorator_name(decorator.func.value)}.{decorator.func.attr}"
            elif isinstance(decorator.func, ast.Name):
                return decorator.func.id
        elif isinstance(decorator, ast.Attribute):
            return f"{self._get_decorator_name(decorator.value)}.{decorator.attr}"
        elif isinstance(decorator, ast.Name):
            return decorator.id
        return ""

    def _is_mcp_tool_decorator(self, decorator: ast.expr) -> bool:
        """Check if a decorator is @mcp.tool()"""
        decorator_name = self._get_decorator_name(decorator)
        return decorator_name == "mcp.tool"

    def _get_function_source(self, node: ast.FunctionDef) -> str:
        """Extract the source code of a function"""
        start_line = node.lineno - 1  # AST line numbers are 1-indexed
        end_line = node.end_lineno

        # Get the lines of the function
        lines = self.source_code.splitlines()[start_line:end_line]

        # Include decorators
        decorator_lines = []
        for decorator in node.decorator_list:
            decorator_start = decorator.lineno - 1
            decorator_end = getattr(decorator, 'end_lineno', decorator.lineno)
            decorator_lines.extend(self.source_code.splitlines()[decorator_start:decorator_end])

        # Combine decorator lines and function lines
        return '\n'.join(decorator_lines + lines)

    def _get_docstring(self, node: ast.FunctionDef) -> str:
        """Extract the docstring of a function"""
        docstring = ast.get_docstring(node)
        return docstring if docstring else ""

    def _get_function_signature(self, node: ast.FunctionDef) -> Dict[str, Any]:
        """Extract the function signature including parameters and return type"""
        params = {}
        for arg in node.args.args:
            param_name = arg.arg
            param_type = ""
            if arg.annotation:
                param_type = ast.unparse(arg.annotation)
            params[param_name] = param_type

        return_type = ""
        if node.returns:
            return_type = ast.unparse(node.returns)

        return {
            "parameters": params,
            "return_type": return_type
        }

    def extract_tool_functions(self) -> List[Dict[str, Any]]:
        """
        Extract all functions decorated with @mcp.tool()

        Returns:
            A list of dictionaries containing function information
        """
        tool_functions = []

        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef) :
                # Check if the function has decorators
                for decorator in node.decorator_list:
                    if self._is_mcp_tool_decorator(decorator):
                        function_info = {
                            "name": node.name,
                            "source_code": self._get_function_source(node),
                            "docstring": self._get_docstring(node),
                            "signature": self._get_function_signature(node),
                            "line_number": node.lineno
                        }
                        tool_functions.append(function_info)
                        break

        return tool_functions

def extract_tools(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract tool functions from a file

    Args:
        file_path: Path to the Python file

    Returns:
        A list of dictionaries containing function information
    """
    extractor = ToolFunctionExtractor(file_path)
    return extractor.extract_tool_functions()

def print_tool_function_info(function_info: Dict[str, Any]) -> None:
    """
    Print information about a tool function in a readable format

    Args:
        function_info: Dictionary containing function information
    """
    print(f"Function: {function_info['name']}")
    print(f"Line number: {function_info['line_number']}")
    print("\nDocstring:")
    print(f"{function_info['docstring']}")
    print("\nSignature:")
    params = function_info['signature']['parameters']
    for param_name, param_type in params.items():
        print(f"  {param_name}: {param_type}")
    print(f"Return type: {function_info['signature']['return_type']}")
    print("\nSource code:")
    print(f"{function_info['source_code']}")
    print("\n" + "-" * 80 + "\n")

# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parse_python.py <dir>")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)

    try:
        tool_functions = extract_tools(file_path)

        if not tool_functions:
            print(f"No functions decorated with @mcp.tool() found in '{file_path}'.")
        else:
            print(f"Found {len(tool_functions)} tool functions in '{file_path}':\n")
            for function_info in tool_functions:
                print_tool_function_info(function_info)

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)