#!/usr/bin/env python3
"""
Dependency Version Checker

This script checks the latest versions of iOS and Android dependencies
by querying GitHub repositories and outputs the results to docs/data.json.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import re
import time # For potential retries or delays

# --- Configuration ---
# Set to True to enable verbose debugging output
DEBUG_MODE = os.environ.get('DEBUG_CHECK_VERSIONS', 'False').lower() == 'true'

# API request timeout in seconds
REQUEST_TIMEOUT = 15

# --- Dependencies ---
# Consider moving this to a separate JSON file (e.g., input_dependencies.json) for easier management
IOS_DEPENDENCIES = [
    {
        "name": "AlertToast",
        "url": "https://github.com/elai950/AlertToast",
        "current": "1.3.9"
    },
    {
        "name": "Firebase",
        "url": "https://github.com/firebase/firebase-ios-sdk", # Removed .git
        "current": "10.0.0"
    },
    {
        "name": "Lottie",
        "url": "https://github.com/airbnb/lottie-ios",
        "current": "4.0.0"
    },
    {
        "name": "Mantis",
        "url": "https://github.com/guoyingtao/Mantis",
        "current": "2.8.0"
    },
    {
        "name": "Reachability",
        "url": "https://github.com/ashleymills/Reachability.swift",
        "current": "master"
    },
    {
        "name": "SDWebImageSwiftUI",
        "url": "https://github.com/SDWebImage/SDWebImageSwiftUI",
        "current": "3.1.3"
    },
    {
        "name": "GoogleMobileAds",
        "url": "https://github.com/googleads/swift-package-manager-google-mobile-ads",
        "current": "11.0.0"
    },
    {
        "name": "GoogleUserMessagingPlatform",
        "url": "https://github.com/googleads/swift-package-manager-user-messaging", # Removed .git
        "current": "2.1.0"
    },
    {
        "name": "swiftui-introspect",
        "url": "https://github.com/siteline/SwiftUI-Introspect", # Removed .git
        "current": "0.2.3"
    },
    {
        "name": "TOCropViewController",
        "url": "https://github.com/TimOliver/TOCropViewController",
        "current": "2.6.1"
    }
]

# --- Helper Functions ---

def log_debug(message: str):
    """Prints a message only if DEBUG_MODE is True."""
    if DEBUG_MODE:
        print(f"DEBUG: {message}")

def parse_github_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse GitHub URL to extract owner and repository name.
    Handles URLs with or without .git suffix and potential trailing slashes.
    """
    if not url:
        return None, None
    # Remove .git suffix if present
    if url.endswith('.git'):
        url = url[:-4]
    
    # Remove trailing slash if present
    url = url.rstrip('/')

    # Regex to capture owner and repo from various GitHub URL formats
    pattern = r'^(?:https|git)://github\.com/([^/]+)/([^/]+?)(?:\.git)?$'
    match = re.match(pattern, url)
    
    if match:
        owner = match.group(1)
        repo = match.group(2)
        log_debug(f"Parsed URL '{url}' -> Owner: '{owner}', Repo: '{repo}'")
        return owner, repo
    
    log_debug(f"Failed to parse GitHub URL: '{url}'")
    return None, None


def make_github_request(url: str) -> Optional[Dict[str, Any]]:
    """
    Make a request to GitHub API with proper headers and error handling.
    """
    headers = {
        'User-Agent': 'Dependency-Version-Checker/1.0 (Python Script)',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    github_token = os.environ.get('GITHUB_TOKEN')
    if github_token:
        headers['Authorization'] = f'token {github_token}'
        log_debug(f"Using GITHUB_TOKEN for request to {url}")
    else:
        log_debug(f"No GITHUB_TOKEN found for request to {url}. Rate limits will be lower.")
    
    log_debug(f"Making GET request to: {url} with headers: {headers if DEBUG_MODE else '...'}")

    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            response_body = response.read().decode('utf-8')
            log_debug(f"Response status {response.status} for {url}. Body (first 200 chars): {response_body[:200]}")
            
            if response.status == 200:
                return json.loads(response_body)
            else:
                print(f"WARN: GitHub API returned HTTP {response.status} for {url}. Body: {response_body}")
                return None
    except HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode('utf-8')
        except Exception:
            pass # Ignore if can't read body
        print(f"ERROR: HTTP Error {e.code} for {url}: {e.reason}. Response body: {error_body}")
        if e.code == 403 and "rate limit exceeded" in error_body.lower():
            print("ERROR: GitHub API rate limit exceeded. Please use a GITHUB_TOKEN or wait.")
        elif e.code == 404:
            print(f"INFO: Resource not found at {url} (404). This might be expected (e.g., no /releases/latest).")
        return None
    except URLError as e:
        print(f"ERROR: URL Error for {url}: {e.reason}")
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to decode JSON response from {url}: {e}")
        return None
    except Exception as e:
        print(f"ERROR: Unexpected error during request to {url}: {type(e).__name__} - {e}")
        return None


def get_latest_release(owner: str, repo: str) -> Optional[str]:
    """
    Get the latest release tag_name for a GitHub repository.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    log_debug(f"Fetching latest release from: {url}")
    data = make_github_request(url)
    
    if data and 'tag_name' in data:
        tag_name = data['tag_name']
        log_debug(f"Latest release tag for {owner}/{repo}: {tag_name}")
        return tag_name
    log_debug(f"No 'tag_name' found in latest release data for {owner}/{repo} or data is None.")
    return None


def get_latest_tag(owner: str, repo: str) -> Optional[str]:
    """
    Get the latest tag name for a GitHub repository.
    This often requires sorting tags semantically if multiple are returned.
    For simplicity, this implementation takes the first tag, assuming GitHub API returns them sorted by date (often true).
    A more robust solution would involve semantic version parsing and sorting.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    log_debug(f"Fetching tags from: {url}")
    data = make_github_request(url)
    
    if data and isinstance(data, list) and len(data) > 0:
        # Assuming the first tag in the list is the most recent one published.
        # GitHub API usually returns tags in reverse chronological order (newest first).
        tag_name = data[0].get('name')
        if tag_name:
            log_debug(f"Latest tag for {owner}/{repo} (from list): {tag_name}")
            return tag_name
    log_debug(f"No tags found or data is not a list for {owner}/{repo}.")
    return None


def get_latest_commit_sha(owner: str, repo: str, branch_name: str) -> Optional[str]:
    """
    Get the latest commit SHA for a specific branch. Tries common default branches if the provided one fails.
    """
    branches_to_try = [branch_name]
    if branch_name.lower() == "master" and "main" not in branches_to_try:
        branches_to_try.append("main")
    elif branch_name.lower() == "main" and "master" not in branches_to_try:
        branches_to_try.append("master")
    
    for branch in branches_to_try:
        url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"
        log_debug(f"Fetching latest commit SHA for {owner}/{repo} on branch '{branch}' from: {url}")
        data = make_github_request(url)
        
        if data and isinstance(data, dict) and 'commit' in data and isinstance(data['commit'], dict) and 'sha' in data['commit']:
            sha = data['commit']['sha']
            short_sha = sha[:7] # Standard short SHA
            log_debug(f"Latest commit SHA for {owner}/{repo} on branch '{branch}': {short_sha} (full: {sha})")
            return short_sha
        log_debug(f"Could not get commit SHA for {owner}/{repo} on branch '{branch}'.")
    
    log_debug(f"Failed to get commit SHA for {owner}/{repo} on any attempted branches: {branches_to_try}")
    return None


def determine_status(current_version: str, latest_version: Optional[str], is_tracking_branch: bool, has_error: bool) -> str:
    """
    Determine the dependency status.
    """
    if has_error or latest_version is None:
        return "🚨 Error Checking"
    
    if is_tracking_branch:
        # For branches, we can't easily say "up to date" without comparing SHAs,
        # but 'current' is the branch name, 'latest' is the SHA.
        # We'll just mark it as tracking.
        return "ℹ️ Tracks Branch"
    
    # Normalize versions for comparison (e.g., remove 'v' prefix)
    norm_current = current_version.lstrip('vV')
    norm_latest = latest_version.lstrip('vV')

    if norm_current == norm_latest:
        return "✅ Up to Date"
    
    # Basic semantic version check (not perfect but good enough for many cases)
    try:
        from packaging.version import parse as parse_version
        if parse_version(norm_current) >= parse_version(norm_latest):
            return "✅ Up to Date" # Current is newer or same (e.g. pre-release)
    except ImportError:
        log_debug("`packaging` library not found. Falling back to simple string comparison for versions.")
    except Exception as e:
        log_debug(f"Error comparing versions '{norm_current}' and '{norm_latest}' with packaging.version: {e}")


    return "⚠️ Update Available"


def check_dependency_version(dependency_config: Dict[str, str]) -> Dict[str, Any]:
    """
    Check the version status of a single dependency.
    """
    name = dependency_config['name']
    repo_url = dependency_config['url']
    current_version = dependency_config['current']
    
    print(f"Checking {name} ({repo_url})...")
    
    owner, repo_name = parse_github_url(repo_url)
    
    if not owner or not repo_name:
        return {
            "name": name,
            "url": repo_url,
            "current": current_version,
            "latest": "Unknown",
            "status": "🚨 Error Checking",
            "notes": "Could not parse GitHub URL"
        }
    
    is_tracking_branch = current_version.lower() in ['master', 'main', 'develop', 'dev', 'mainline'] # Add more if needed
    latest_version: Optional[str] = None
    notes = ""
    has_error = False

    if is_tracking_branch:
        latest_version = get_latest_commit_sha(owner, repo_name, current_version)
        notes = f"Tracking '{current_version}' branch."
        if latest_version is None:
            notes += " Could not fetch latest commit."
            has_error = True
    else:
        # Try /releases/latest first
        latest_version = get_latest_release(owner, repo_name)
        
        if latest_version is None:
            log_debug(f"No latest release found for {name}, trying latest tag...")
            # Fallback to /tags
            latest_version = get_latest_tag(owner, repo_name)
            if latest_version:
                notes = "Latest version from tags (no formal release found)."
            else:
                notes = "Could not fetch latest release or tag."
                has_error = True
        else:
            notes = "Latest version from releases."

    if latest_version is None and not has_error: # Should be caught by has_error logic above
        latest_version = "Unknown"
        has_error = True
        if not notes: notes = "Could not determine latest version."


    status = determine_status(current_version, latest_version, is_tracking_branch, has_error)
    
    result = {
        "name": name,
        "url": repo_url,
        "current": current_version,
        "latest": latest_version if latest_version is not None else "Unknown",
        "status": status
    }
    if notes: # Add notes only if they are non-empty
        result["notes"] = notes.strip()
    
    return result


def main():
    """Main function to check all dependencies and generate data.json."""
    start_time_iso = datetime.now(timezone.utc).isoformat()
    print("🔍 Checking dependency versions...")
    print(f"📅 Started at: {start_time_iso}")
    if DEBUG_MODE:
        print("--- DEBUG MODE ENABLED ---")
    
    all_results: List[Dict[str, Any]] = []
    
    dependencies_to_check = IOS_DEPENDENCIES # Later, this could be extended or loaded from a file
    
    for dep_config in dependencies_to_check:
        # Optional: Add a small delay between requests if still hitting secondary rate limits
        # time.sleep(0.5) # 0.5 second delay
        result = check_dependency_version(dep_config)
        all_results.append(result)
        
        status_symbol = result['status'].split()[0] # Get the emoji
        print(f"  {status_symbol} {result['name']}: {result['current']} → {result['latest']}")
        if 'notes' in result and result['notes']:
            print(f"    Notes: {result['notes']}")

    output_data = {
        "last_updated_utc": start_time_iso, # Store the start time
        "dependencies": all_results
    }
    
    # Ensure docs directory exists
    docs_dir = 'docs'
    os.makedirs(docs_dir, exist_ok=True)
    
    output_file_path = os.path.join(docs_dir, 'data.json')
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Version check complete!")
        print(f"📄 Results written to {output_file_path}")
    except IOError as e:
        print(f"\n❌ ERROR: Could not write results to {output_file_path}: {e}")
        sys.exit(1)
    
    # Summary statistics
    total = len(all_results)
    up_to_date = len([r for r in all_results if "✅" in r['status']])
    updates_available = len([r for r in all_results if "⚠️" in r['status']])
    tracking_branch = len([r for r in all_results if "ℹ️" in r['status']])
    errors = len([r for r in all_results if "🚨" in r['status']])
    
    print(f"\n📊 Summary:")
    print(f"  Total dependencies: {total}")
    print(f"  Up to date: {up_to_date}")
    print(f"  Updates available: {updates_available}")
    print(f"  Tracking branches: {tracking_branch}")
    print(f"  Errors: {errors}")

    if errors > 0:
        print("\n⚠️ Some dependencies encountered errors. Please check the logs.")

if __name__ == "__main__":
    main()