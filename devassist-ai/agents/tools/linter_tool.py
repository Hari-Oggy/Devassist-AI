import subprocess
import tempfile
import os
import json


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


def checkstyle_analysis(file_path: str) -> str:
    """Runs Checkstyle or javac static analysis on a Java file. Input should be an absolute file path."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} does not exist."
    if not file_path.endswith('.java'):
        return f"Error: File {file_path} is not a Java file."

    # Try checkstyle first (more comprehensive)
    try:
        result = subprocess.run(
            ["checkstyle", "-c", "/google_checks.xml", "-f", "plain", file_path],
            capture_output=True, text=True, timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        if output and "Starting audit" in output:
            lines = [l for l in output.splitlines()
                     if l.strip() and "Starting audit" not in l and "Audit done" not in l]
            if not lines:
                return "No issues found."
            formatted = [f"CHECKSTYLE RESULTS for {os.path.basename(file_path)}:\n"]
            formatted.extend(lines[:20])  # Cap at 20 issues
            return "\n".join(formatted)
    except FileNotFoundError:
        pass  # Checkstyle not installed, try javac
    except Exception:
        pass

    # Fallback: javac syntax check (always available if JDK is installed)
    try:
        result = subprocess.run(
            ["javac", "-Xlint:all", "-d", tempfile.gettempdir(), file_path],
            capture_output=True, text=True, timeout=30,
        )
        errors = result.stderr.strip()
        if not errors:
            return "No issues found."
        formatted = [f"JAVAC LINT RESULTS for {os.path.basename(file_path)}:\n"]
        for line in errors.splitlines()[:15]:  # Cap at 15 lines
            formatted.append(line)
        return "\n".join(formatted)
    except FileNotFoundError:
        return "No Java linter available (checkstyle/javac not found)."
    except subprocess.TimeoutExpired:
        return "Error: Java analysis timed out after 30 seconds."
    except Exception as e:
        return f"Error running Java linter: {str(e)}"


def go_lint_analysis(file_path: str) -> str:
    """Runs Go static analysis using golangci-lint or go vet."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} does not exist."
    if not file_path.endswith('.go'):
        return f"Error: File {file_path} is not a Go file."

    # Try golangci-lint first
    try:
        result = subprocess.run(
            ["golangci-lint", "run", "--out-format=json", file_path],
            capture_output=True, text=True, timeout=30
        )
        if result.stdout.strip():
            issues = json.loads(result.stdout)
            formatted = [f"GOLANGCI-LINT RESULTS for {os.path.basename(file_path)}:\n"]
            for issue in issues.get("Issues", [])[:20]:
                line = issue.get("Pos", {}).get("Line", "?")
                msg = issue.get("Text", "")
                linter = issue.get("FromLinter", "unknown")
                formatted.append(f"Line {line} [{linter}]: {msg}")
            if len(formatted) > 1:
                return "\n".join(formatted)
    except FileNotFoundError:
        pass # fallback to go vet
    except Exception:
        pass

    # Fallback to go vet
    try:
        result = subprocess.run(
            ["go", "vet", file_path],
            capture_output=True, text=True, timeout=30
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "No issues found."
        formatted = [f"GO VET RESULTS for {os.path.basename(file_path)}:\n"]
        formatted.extend(output.splitlines()[:20])
        return "\n".join(formatted)
    except FileNotFoundError:
        return "Go toolchain not available (go vet not found)."
    except subprocess.TimeoutExpired:
        return "Error: Go analysis timed out."
    except Exception as e:
        return f"Error running go vet: {str(e)}"

def rust_lint_analysis(file_path: str) -> str:
    """Runs Rust static analysis using cargo clippy."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} does not exist."
    
    file_dir = os.path.dirname(file_path)
    try:
        # Run clippy in the file's directory
        result = subprocess.run(
            ["cargo", "clippy", "--message-format=short", "--quiet"],
            cwd=file_dir, capture_output=True, text=True, timeout=60
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "No issues found."
            
        # Filter for the specific file
        file_basename = os.path.basename(file_path)
        lines = [l for l in output.splitlines() if file_basename in l and ("error:" in l or "warning:" in l)]
        if not lines:
            return "No issues found."
            
        formatted = [f"CARGO CLIPPY RESULTS for {file_basename}:\n"]
        formatted.extend(lines[:20])
        return "\n".join(formatted)
    except FileNotFoundError:
        return "Rust toolchain (cargo clippy) not available."
    except subprocess.TimeoutExpired:
        return "Error: Rust analysis timed out."
    except Exception as e:
        return f"Error running Rust linter: {str(e)}"

def cpp_lint_analysis(file_path: str) -> str:
    """Runs C/C++ static analysis using cppcheck."""
    if not os.path.exists(file_path):
        return f"Error: File {file_path} does not exist."
        
    try:
        result = subprocess.run(
            ["cppcheck", "--enable=all", "--inconclusive", "--template=gcc", file_path],
            capture_output=True, text=True, timeout=30
        )
        # cppcheck outputs to stderr
        output = result.stderr.strip()
        if not output:
            return "No issues found."
            
        lines = [l for l in output.splitlines() if "information:" not in l.lower()]
        if not lines:
            return "No issues found."
            
        formatted = [f"CPPCHECK RESULTS for {os.path.basename(file_path)}:\n"]
        formatted.extend(lines[:20])
        return "\n".join(formatted)
    except FileNotFoundError:
        return "cppcheck not available."
    except subprocess.TimeoutExpired:
        return "Error: cppcheck analysis timed out."
    except Exception as e:
        return f"Error running cppcheck: {str(e)}"

# ─── Extension → Linter Mapping ──────────────────────────────────────────────

LINTER_MAP = {
    ".py": pylint_analysis,
    ".js": eslint_analysis,
    ".ts": eslint_analysis,
    ".jsx": eslint_analysis,
    ".tsx": eslint_analysis,
    ".java": checkstyle_analysis,
    ".go": go_lint_analysis,
    ".rs": rust_lint_analysis,
    ".c": cpp_lint_analysis,
    ".cpp": cpp_lint_analysis,
    ".h": cpp_lint_analysis,
    ".hpp": cpp_lint_analysis,
    ".cc": cpp_lint_analysis,
    ".cxx": cpp_lint_analysis,
}


def run_linter(filename: str) -> str:
    """
    Run the appropriate linter for a file based on its extension.
    Returns linter output string, or empty string if no linter available.
    """
    ext = os.path.splitext(filename)[1].lower()
    linter = LINTER_MAP.get(ext)
    if not linter:
        return ""
    try:
        result = linter(filename)
        if result and "No issues found" not in result and "not available" not in result:
            return result
    except Exception:
        pass
    return ""


LINTER_TOOLS = [pylint_analysis, eslint_analysis, checkstyle_analysis, go_lint_analysis, rust_lint_analysis, cpp_lint_analysis]

