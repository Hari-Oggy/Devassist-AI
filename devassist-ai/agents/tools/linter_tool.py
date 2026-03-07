import subprocess
import tempfile
import os
import json
from langchain_core.tools import tool

@tool
def pylint_analysis(file_path: str) -> str:
    """Runs Pylint static analysis on a Python file. Input should be an absolute file path. Returns linting results with line numbers and issue descriptions."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} does not exist."
    if not file_path.endswith('.py'):
        return f"Error: File {file_path} is not a Python file."
        
    try:
        result = subprocess.run(
            ["pylint", "--output-format=json", file_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout
        
        if not output.strip():
            return "No issues found."
            
        issues = json.loads(output)
        if not issues:
            return "No issues found."
            
        formatted_issues = [f"PYLINT RESULTS for {os.path.basename(file_path)}:\n"]
        for issue in issues:
            line = issue.get("line", "?")
            msg_type = issue.get("type", "unknown")
            symbol = issue.get("symbol", "unknown")
            message = issue.get("message", "")
            formatted_issues.append(f"Line {line} [{msg_type}] {symbol}: {message}")
            
        return "\n".join(formatted_issues)
    except subprocess.TimeoutExpired:
        return f"Error: Pylint analysis timed out after 30 seconds."
    except json.JSONDecodeError:
        return f"Error: Failed to parse Pylint JSON output."
    except Exception as e:
        return f"Error running pylint: {str(e)}"

@tool
def eslint_analysis(file_path: str) -> str:
    """Runs ESLint static analysis on a JavaScript/TypeScript file. Input should be an absolute file path."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} does not exist."
    
    valid_exts = {'.js', '.ts', '.jsx', '.tsx'}
    ext = os.path.splitext(file_path)[1]
    if ext not in valid_exts:
        return f"Error: File {file_path} has unsupported extension {ext}."
        
    try:
        result = subprocess.run(
            ["npx", "eslint", "--format=json", file_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0 and "not found" in result.stderr.lower():
            return "ESLint not available. Install with: npm install -g eslint"
            
        output = result.stdout
        if not output.strip():
            return "No issues found."
            
        issues_list = json.loads(output)
        if not issues_list or len(issues_list) == 0:
            return "No issues found."
            
        file_issues = issues_list[0].get("messages", [])
        if not file_issues:
            return "No issues found."
            
        formatted_issues = [f"ESLINT RESULTS for {os.path.basename(file_path)}:\n"]
        for issue in file_issues:
            line = issue.get("line", "?")
            msg_type = "error" if issue.get("severity") == 2 else "warning"
            rule_id = issue.get("ruleId", "unknown")
            message = issue.get("message", "")
            formatted_issues.append(f"Line {line} [{msg_type}] {rule_id}: {message}")
            
        return "\n".join(formatted_issues)
        
    except subprocess.TimeoutExpired:
        return f"Error: ESLint analysis timed out after 30 seconds."
    except json.JSONDecodeError:
        return f"Error: Failed to parse ESLint JSON output."
    except FileNotFoundError:
        return "ESLint not available. Install with: npm install -g eslint"
    except Exception as e:
        return f"Error running eslint: {str(e)}"

LINTER_TOOLS = [pylint_analysis, eslint_analysis]
