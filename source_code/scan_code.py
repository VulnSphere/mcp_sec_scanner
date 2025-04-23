#!/usr/bin/env python3
# coding=utf-8
import os
import json
import threading
import concurrent.futures
import argparse
import csv
from typing import Dict, List, Any, Optional
import openai
from parse_python import extract_tools
from dotenv import load_dotenv
import time
import random

load_dotenv()

class ToolAnalyzer:
    """
    A class to analyze tools in subfolders of a specified directory
    """

    def __init__(self, debug: bool = False):
        """
        Initialize with the root directory to analyze

        Args:
            debug: Enable debug output
        """
        self.debug = debug

        self.client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'), base_url=os.environ.get('BASE_URL'))

        # Create a lock for thread-safe operations
        self.lock = threading.Lock()

    def get_code_files(self, repo_path: str, language: str = 'Python') -> List[str]:
        """
        Get a list of all code files in a repository

        Args:
            repo_path: Path to the repository
            language: Programming language to filter by

        Returns:
            List of code file paths
        """

        if language == 'Python':
            extension = '.py'
        elif language == 'Go':
            extension = '.go'
        elif language == 'Java':
            extension = '.java'
        elif language == 'JavaScript':
            extension = '.js'
        elif language == 'TypeScript':
            extension = '.ts'
        elif language == 'C':
            extension = '.c'
        elif language == 'C++':
            extension = '.cpp'
        elif language == 'C#':
            extension = '.cs'
        elif language == 'Ruby':
            extension = '.rb'
        elif language == 'PHP':
            extension = '.php'
        elif language == 'Swift':
            extension = '.swift'
        elif language == 'Kotlin':
            extension = '.kt'
        elif language == 'Rust':
            extension = '.rs'
        elif language == 'HTML':
            extension = '.html'
        elif language == 'CSS':
            extension = '.css'
        else:
            # For other languages, use lowercase version as extension
            extension = f'.{language.lower()}'

        code_files = []
        for root, _, files in os.walk(repo_path):
            for file in files:
                if "site-packages" in file or "node_modules" in file or ".venv" in file:
                    continue
                if file.endswith(extension):
                    code_files.append(os.path.join(root, file))

        if self.debug:
            print(f"Found {len(code_files)} {language} files in {repo_path}")
            for file in code_files:
                print(f"  - {file}")

        return code_files

    def analyze_tool_with_llm(self, tool_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a tool function using LLM with retry mechanism and JSON validation

        Args:
            tool_info: Dictionary containing tool function information

        Returns:
            Dictionary with analysis results
        """
        # Helper function to validate JSON format
        def is_valid_json(json_str: str) -> bool:
            try:
                json.loads(json_str)
                return True
            except json.JSONDecodeError:
                return False

        # Create a prompt for LLM
        prompt = f"""
Analyze the following function to find out unexcepted behaviors.

Function Name: {tool_info['name']}

Function Doc:
{tool_info['docstring']}

Source Code:
{tool_info['source_code']}

Detection:
1. Judge whether the function described in the Doc is consistent with the logic in the source code, only focus on the logical, and do not focus on the implementation details of the syntax.
2. Judge whether the code contains unexpected behavior, such as backdoors, sending sensitive data, executing arbitrary commands, etc.

Output:
the output should be formated as json
the score if between [0, 100], 0 is the worst, 100 is the best
if the code related to Backdoor, Sensitive Data, unexcepted behavior, the score is 0

{{
    "score": xxx,
    "reason": "..."
}}
"""

        max_retries = 3
        retry_count = 0
        backoff_factor = 2

        while retry_count < max_retries:
            try:
                # Call LLM API
                response = self.client.chat.completions.create(
                    model="anthropic/claude-3.7-sonnet",
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )

                # Extract the analysis from the response
                analysis = response.choices[0].message.content

                # Add the analysis to the tool info
                tool_info["analysis"] = analysis

                if self.debug:
                    print(f"Successfully analyzed tool: {tool_info['name']}")

                return tool_info

            except Exception as e:
                if self.debug:
                    print(f"Error analyzing tool {tool_info['name']}: {str(e)}. Attempt {retry_count + 1}/{max_retries}")

                # If this is the last retry, return with error
                if retry_count == max_retries - 1:
                    # Add error message to the tool info
                    tool_info["analysis"] = f"Error during analysis after {max_retries} attempts: {str(e)}"
                    return tool_info

                # Otherwise, retry with exponential backoff
                retry_count += 1
                sleep_time = (backoff_factor ** retry_count) + random.uniform(0, 1)
                if self.debug:
                    print(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)

        # This should never be reached, but just in case
        tool_info["analysis"] = f"Failed to analyze after {max_retries} attempts"
        return tool_info

    def analyze_repo(self, repo_path: str, language: str = 'Python') -> Dict[str, Any]:
        """
        Analyze all code files in a repository

        Args:
            repo_path: Path to the repository
            language: Programming language to filter by

        Returns:
            Dictionary with analysis results
        """

        # Get all code files in the repository
        code_files = self.get_code_files(repo_path, language)

        # Extract tool functions from each file
        all_tools = []
        for file_path in code_files:
            try:
                tools = extract_tools(file_path)
                if tools:
                    # Add file path to each tool
                    for tool in tools:
                        tool["file_path"] = os.path.relpath(file_path, repo_path)
                    all_tools.extend(tools)
            except Exception as e:
                if self.debug:
                    print(f"Error extracting tools from {file_path}: {str(e)}")

        if self.debug:
            print(f"Found {len(all_tools)} tools in repository {repo_path}")

        # Analyze each tool using OpenAI
        worker_count = min(10, len(all_tools)+1)
        with concurrent.futures.ThreadPoolExecutor(worker_count) as executor:
            # Submit all tasks
            future_to_tool = {
                executor.submit(self.analyze_tool_with_llm, tool): tool
                for tool in all_tools
            }

            # Process results as they complete
            analyzed_tools = []
            for future in concurrent.futures.as_completed(future_to_tool):
                tool = future_to_tool[future]
                try:
                    analyzed_tool = future.result()
                    analyzed_tools.append(analyzed_tool)
                    if self.debug:
                        print(f"Completed analysis for tool: {tool['name']}")
                except Exception as e:
                    if self.debug:
                        print(f"Error processing tool {tool['name']}: {str(e)}")

        # Create the result dictionary
        result = {
            "repo_name": repo_path,
            "tools_count": len(analyzed_tools),
            "tools": analyzed_tools
        }


        return result

    def read_repos_from_csv(self, csv_path: str, language_filter: Optional[str] = None) -> List[str]:
        """
        Read repository information from a CSV file and filter by language if specified

        Args:
            csv_path: Path to the CSV file
            language_filter: Optional language to filter repositories by

        Returns:
            List of repository paths to analyze
        """
        repo_paths = []

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Check if the required columns exist
                    if 'username' not in row or 'repo_name' not in row:
                        if self.debug:
                            print(f"Warning: CSV row missing required columns: {row}")
                        continue

                    # Filter by language if specified
                    if language_filter and 'language' in row:
                        if row['language'] != language_filter:
                            continue

                    # Construct the repository path (username_reponame)
                    repo_name = f"{row['username']}_{row['repo_name']}"
                    repo_path = os.path.join("mcp_repos", repo_name)

                    # Check if the repository directory exists
                    if os.path.isdir(repo_path):
                        repo_paths.append(repo_path)
                    elif self.debug:
                        print(f"Warning: Repository directory not found: {repo_path}")

            if self.debug:
                print(f"Found {len(repo_paths)} repositories from CSV matching criteria")
                for path in repo_paths:
                    print(f"  - {path}")

        except Exception as e:
            if self.debug:
                print(f"Error reading CSV file {csv_path}: {str(e)}")

        return repo_paths


    def analyze_repos(self, csv_path: str, language_filter: Optional[str] = None):
        """
        Analyze repositories listed in a CSV file

        Args:
            csv_path: Path to the CSV file
            language_filter: Optional language to filter repositories by
        """
        if not os.path.isfile(csv_path):
            print(f"Error: CSV file does not exist: {csv_path}")
            return

        repo_paths = self.read_repos_from_csv(csv_path, language_filter)

        if not repo_paths:
            print(f"No repositories found in CSV file matching criteria")
            return

        for repo_path in repo_paths:
            analysis_file = f"{repo_path}_tools.json"
            if os.path.exists(analysis_file):
                print(f"Skipping analysis of {repo_path} (already analyzed)")
                continue

            result = self.analyze_repo(repo_path)

            # Save the result to a JSON file
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)

            if self.debug:
                print(f"Saved analysis results to {analysis_file}")

def main():
    """Main function to run the tool analyzer"""
    parser = argparse.ArgumentParser(description='Analyze tools in subfolders')
    parser.add_argument('--repo', help='Analyze a specific repository')
    parser.add_argument('--csv', help='Path to CSV file containing repository information')
    parser.add_argument('--language', default='Python', help='Filter repositories by language (only used with --csv)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')

    args = parser.parse_args()

    # Validate arguments
    if args.repo and args.csv:
        print("Error: Cannot specify both --repo and --csv options")
        return

    if args.language and not args.csv:
        print("Warning: --language option is only used with --csv option")

    # Create results directory if it doesn't exist
    os.makedirs("./results", exist_ok=True)

    # Create analyzer instance
    analyzer = ToolAnalyzer(args.debug)

    # Analyze based on provided options
    if args.repo:
        # Analyze specific repository
        analyzer.analyze_repo(args.repo, args.language)
    elif args.csv:
        # Analyze repositories from CSV
        analyzer.analyze_repos(args.csv, args.language)

if __name__ == "__main__":
    main()
