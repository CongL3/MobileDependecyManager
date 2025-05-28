#!/usr/bin/env python3
"""
Project Dependency Version Checker (SPM from Package.resolved)

This script fetches and parses the Package.resolved file from a specified
iOS project repository, identifies its Swift Package Manager (SPM) dependencies,
and checks their latest available versions.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from urllib.request import Request, urlopen, build_opener, HTTPErrorProcessor, HTTPCookieProcessor
from urllib.error import HTTPError, URLError
import re
import base64 # For decoding GitHub file content
import http.cookiejar # For GitHub raw file access with token

# --- Configuration ---
PRIMARY_PROJECT_REPO_URL = "https://github.com/CongL3/AnniversaryTracker"
# Optional: Specify a branch or commit SHA for the primary project.
# If None, it will try to use the default branch of the project repo.
PRIMARY_PROJECT_REF = None # e.g., "main", "develop", "a1b2c3d4"

# Path to Package.resolved within the project repository.
# Common paths: "YourProjectName.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
# or "YourProjectName.xcworkspace/xcshareddata/swiftpm/Package.resolved"
# For simple SPM projects, it might be at the root: "Package.resolved"
# Adjust this based on your project structure.
PACKAGE_RESOLVED_PATH = "AnniversaryTracker.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
# If your Package.resolved is at the root of the repo, use:
# PACKAGE_RESOLVED_PATH = "Package.resolved"


# Set to True to enable verbose debugging output
DEBUG_MODE = os.environ.get('DEBUG_CHECK_VERSIONS', 'False').lower() == 'true'
REQUEST_TIMEOUT = 20 # Increased timeout for potentially larger file downloads

# --- Helper Functions (some reused and adapted from check_versions.py) ---

def log_debug(message: str):
    if DEBUG_MODE:
        print(f"DEBUG: {message}")

def parse_github_url_to_owner_repo(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Parses a GitHub URL (e.g., https://github.com/owner/repo.git) to (owner, repo)."""
    if not url:
        return None, None
    
    # Remove .git suffix and trailing slash
    processed_url = url.removesuffix('.git').rstrip('/')
    
    # Regex to capture owner and repo
    pattern = r'^(?:https?|git)://github\.com/([^/]+)/([^/]+)$'
    match = re.match(pattern, processed_url)
    
    if match:
        owner, repo = match.group(1), match.group(2)
        log_debug(f"Parsed URL '{url}' -> Owner: '{owner}', Repo: '{repo}'")
        return owner, repo
    
    log_debug(f"Failed to parse GitHub URL to owner/repo: '{url}'")
    return None, None

def make_api_request(url: str, token: Optional[str] = None, is_raw_download: bool = False) -> Optional[Any]:
    """
    Makes a request, either to GitHub API or for raw file download.
    Returns JSON dict for API calls, or bytes for raw downloads.
    """
    headers = {'User-Agent': 'Project-Dependency-Checker/1.0'}
    if token:
        headers['Authorization'] = f'token {token}'
        log_debug(f"Using GITHUB_TOKEN for request to {url}")
    else:
        log_debug(f"No GITHUB_TOKEN found for request to {url}. Rate limits/access may be restricted.")

    if is_raw_download:
        # For raw.githubusercontent.com, the token might need to be passed differently
        # or sometimes cookies are involved if it's a private repo.
        # For public repos, token in header might not be needed for raw content.
        # However, if the main repo is private, accessing its raw files needs auth.
        # Using a cookie processor can help if GitHub redirects and uses cookies for auth.
        cookie_jar = http.cookiejar.CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookie_jar))
        if token: # GitHub raw sometimes needs token for private repo files
             opener.addheaders = [('Authorization', f'token {token}')]
    else: # API request
        headers['Accept'] = 'application/vnd.github.v3+json'
        opener = build_opener() # Default opener

    opener.addheaders = list(headers.items()) # Add other headers like User-Agent

    log_debug(f"Making GET request to: {url} with headers: {headers if DEBUG_MODE else '...'}")

    try:
        request = Request(url) # Opener will add its headers
        with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
            log_debug(f"Response status {response.status} for {url}")
            if response.status == 200:
                content = response.read()
                if is_raw_download:
                    return content # Return raw bytes
                else:
                    return json.loads(content.decode('utf-8')) # Return parsed JSON
            else:
                print(f"WARN: HTTP {response.status} for {url}. Body: {response.read().decode('utf-8', errors='ignore')[:200]}")
                return None
    except HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode('utf-8', errors='ignore')
        except Exception: pass
        print(f"ERROR: HTTP Error {e.code} for {url}: {e.reason}. Response body: {error_body[:500]}")
        if e.code == 403 and "rate limit exceeded" in error_body.lower():
            print("ERROR: GitHub API rate limit exceeded. Please use a GITHUB_TOKEN or wait.")
        elif e.code == 401 and token: # Unauthorized even with token
             print("ERROR: GitHub Token might be invalid or lack permissions for this resource.")
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

def get_file_content_from_github(owner: str, repo: str, file_path: str, ref: Optional[str], token: Optional[str]) -> Optional[str]:
    """Fetches file content from GitHub API. Content is base64 encoded."""
    ref_param = f"?ref={ref}" if ref else ""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}{ref_param}"
    log_debug(f"Fetching file content from GitHub API: {api_url}")
    
    data = make_api_request(api_url, token)
    if data and 'content' in data and data.get('encoding') == 'base64':
        try:
            decoded_content = base64.b64decode(data['content']).decode('utf-8')
            log_debug(f"Successfully fetched and decoded '{file_path}' from {owner}/{repo}")
            return decoded_content
        except Exception as e:
            print(f"ERROR: Failed to decode base64 content for '{file_path}': {e}")
            return None
    elif data and 'download_url' in data and data['download_url']:
        # Fallback to download_url if content is too large for direct API response
        download_url = data['download_url']
        log_debug(f"File content not directly available, trying download_url: {download_url}")
        raw_content_bytes = make_api_request(download_url, token, is_raw_download=True)
        if raw_content_bytes:
            try:
                return raw_content_bytes.decode('utf-8')
            except UnicodeDecodeError as e:
                print(f"ERROR: Failed to decode content from download_url for '{file_path}': {e}")
                return None
    elif data:
        print(f"ERROR: Unexpected response format for file content of '{file_path}'. Keys: {list(data.keys())}")
    else:
        print(f"ERROR: Failed to fetch file content for '{file_path}' from {owner}/{repo} at ref '{ref}'. Response was None.")

    return None


def parse_package_resolved(content: str) -> List[Dict[str, Any]]:
    """Parses Package.resolved content (v1 or v2) into a list of dependencies."""
    dependencies = []
    try:
        data = json.loads(content)
        version = data.get("version", 1) # Default to v1 if version key is missing

        if version == 1:
            pins = data.get("object", {}).get("pins", [])
            for pin in pins:
                if "repositoryURL" in pin and "state" in pin:
                    dependencies.append({
                        "name": pin.get("package", pin.get("identity", os.path.basename(pin["repositoryURL"].removesuffix(".git")))),
                        "url": pin["repositoryURL"],
                        "resolved_version": pin["state"].get("version") or pin["state"].get("branch") or pin["state"].get("revision","unknown"),
                        "is_branch_or_revision": bool(pin["state"].get("branch") or pin["state"].get("revision"))
                    })
        elif version == 2:
            pins = data.get("pins", [])
            for pin in pins:
                if "location" in pin and "state" in pin:
                    dependencies.append({
                        "name": pin.get("identity", os.path.basename(pin["location"].removesuffix(".git"))), # 'identity' is preferred
                        "url": pin["location"],
                        "resolved_version": pin["state"].get("version") or pin["state"].get("branch") or pin["state"].get("revision","unknown"),
                        "is_branch_or_revision": bool(pin["state"].get("branch") or pin["state"].get("revision"))
                    })
        else:
            print(f"ERROR: Unsupported Package.resolved version: {version}")
            return []
            
        log_debug(f"Parsed {len(dependencies)} dependencies from Package.resolved (v{version})")
        return dependencies
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse Package.resolved JSON content: {e}")
        return []
    except Exception as e:
        print(f"ERROR: Unexpected error parsing Package.resolved: {e}")
        return []

def get_latest_github_version(owner: str, repo: str, token: Optional[str]) -> Tuple[Optional[str], str, bool]:
    """
    Gets the latest version (tag/release) for a GitHub repo.
    Returns (latest_version, type_of_version, is_error).
    Type can be "release", "tag".
    """
    # 1. Try latest release
    release_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    release_data = make_api_request(release_url, token)
    if release_data and 'tag_name' in release_data:
        log_debug(f"Latest release for {owner}/{repo}: {release_data['tag_name']}")
        return release_data['tag_name'], "release", False

    # 2. Fallback to latest tag
    tags_url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    tags_data = make_api_request(tags_url, token)
    if tags_data and isinstance(tags_data, list) and len(tags_data) > 0:
        # Assuming tags are ordered newest first by GitHub API
        latest_tag_name = tags_data[0].get('name')
        if latest_tag_name:
            log_debug(f"Latest tag for {owner}/{repo}: {latest_tag_name}")
            return latest_tag_name, "tag", False
            
    log_debug(f"Could not find releases or tags for {owner}/{repo}")
    return None, "unknown", True

def get_latest_commit_sha(owner: str, repo: str, branch_name: str, token: Optional[str]) -> Optional[str]:
    """Gets the latest commit SHA for a specific branch."""
    branch_url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch_name}"
    branch_data = make_api_request(branch_url, token)
    if branch_data and 'commit' in branch_data and 'sha' in branch_data['commit']:
        sha = branch_data['commit']['sha']
        log_debug(f"Latest commit SHA for {owner}/{repo} on branch '{branch_name}': {sha[:7]}")
        return sha[:7] # Short SHA
    log_debug(f"Could not get commit SHA for {owner}/{repo} on branch '{branch_name}'.")
    return None

def determine_status_for_resolved(resolved_version: str, latest_version: Optional[str], is_branch_or_revision: bool, has_error: bool) -> str:
    if has_error or latest_version is None:
        return "🚨 Error Checking"
    
    if is_branch_or_revision:
        # If resolved_version is a commit SHA, and latest_version is also a commit SHA (from get_latest_commit_sha)
        if len(resolved_version) >= 7 and len(latest_version) >= 7 and resolved_version.startswith(latest_version[:len(resolved_version)]):
             return "✅ Up to Date (Branch/Revision)"
        # If resolved_version is a branch name, latest_version is its SHA.
        # We can only say it's tracking. For a more precise "up to date", we'd need the SHA from Package.resolved's state.revision.
        return f"ℹ️ Tracks Branch/Revision"


    norm_resolved = resolved_version.lstrip('vV')
    norm_latest = latest_version.lstrip('vV')

    if norm_resolved == norm_latest:
        return "✅ Up to Date"
    
    try:
        from packaging.version import parse as parse_version
        if parse_version(norm_resolved) >= parse_version(norm_latest):
            return "✅ Up to Date"
    except ImportError:
        log_debug("`packaging` library not found for semantic version comparison.")
    except Exception: # Catch errors from parse_version if versions are not standard
        log_debug(f"Could not semantically compare '{norm_resolved}' and '{norm_latest}'. Falling back to string comparison.")

    return "⚠️ Update Available"

# --- Main Logic ---
def main():
    start_time_iso = datetime.now(timezone.utc).isoformat()
    print(f"🔍 Project Dependency Checker (SPM from Package.resolved)")
    print(f"📅 Started at: {start_time_iso}")
    print(f"🎯 Primary Project Repo: {PRIMARY_PROJECT_REPO_URL}")
    if PRIMARY_PROJECT_REF:
        print(f"🌲 Using Ref/Branch: {PRIMARY_PROJECT_REF}")
    print(f"📄 Package.resolved Path: {PACKAGE_RESOLVED_PATH}")
    if DEBUG_MODE: print("--- DEBUG MODE ENABLED ---")

    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("⚠️ WARNING: GITHUB_TOKEN environment variable not set. API rate limits will be very low and private repos inaccessible.")

    # 1. Get Package.resolved content from the primary project repo
    project_owner, project_repo = parse_github_url_to_owner_repo(PRIMARY_PROJECT_REPO_URL)
    if not project_owner or not project_repo:
        print(f"❌ ERROR: Could not parse primary project repository URL: {PRIMARY_PROJECT_REPO_URL}")
        sys.exit(1)

    package_resolved_content = get_file_content_from_github(
        project_owner, project_repo, PACKAGE_RESOLVED_PATH, PRIMARY_PROJECT_REF, github_token
    )

    if not package_resolved_content:
        print(f"❌ ERROR: Failed to fetch Package.resolved from '{PRIMARY_PROJECT_REPO_URL}' at path '{PACKAGE_RESOLVED_PATH}'.")
        if not github_token and "private" in PRIMARY_PROJECT_REPO_URL.lower(): # Heuristic
            print("INFO: If the primary project repo is private, a GITHUB_TOKEN with 'repo' scope is required.")
        sys.exit(1)

    # 2. Parse Package.resolved
    resolved_dependencies = parse_package_resolved(package_resolved_content)
    if not resolved_dependencies:
        print("ℹ️ No dependencies found in Package.resolved or failed to parse.")
        # Write empty results if needed by downstream tools
        output_data = {"last_updated_utc": start_time_iso, "project_url": PRIMARY_PROJECT_REPO_URL, "dependencies": []}
        os.makedirs('docs', exist_ok=True)
        with open('docs/project_deps_data.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print("📄 Empty results written to docs/project_deps_data.json")
        sys.exit(0)
    
    print(f"\n🔎 Found {len(resolved_dependencies)} dependencies in Package.resolved. Checking their latest versions...")

    # 3. For each dependency, check its latest version
    final_results = []
    for dep in resolved_dependencies:
        print(f"\nChecking: {dep['name']} ({dep['url']})")
        print(f"  Resolved Version: {dep['resolved_version']} {'(Branch/Rev)' if dep['is_branch_or_revision'] else ''}")

        dep_owner, dep_repo = parse_github_url_to_owner_repo(dep['url'])
        latest_version_val: Optional[str] = None
        status: str
        notes = ""
        has_error_fetching_latest = False

        if not dep_owner or not dep_repo:
            status = "🚨 Error Parsing URL"
            notes = "Could not parse dependency GitHub URL."
            has_error_fetching_latest = True
        else:
            if dep['is_branch_or_revision'] and not dep['resolved_version'].startswith(('v', 'V')) and not re.match(r'^\d+\.\d+', dep['resolved_version']):
                # If it's a branch name (e.g., "main") or a full SHA, try to get the latest commit on that branch.
                # Package.resolved 'state.revision' is the exact commit. 'state.branch' is the branch name.
                # If state.version is present, it's a tag.
                # This logic is a bit complex because Package.resolved's "version" can be a tag,
                # "branch" can be a branch name, and "revision" is a commit SHA.
                # For now, if `is_branch_or_revision` is true, we'll assume `resolved_version` is either a branch name or a commit SHA.
                # If it's a branch name, we fetch the latest SHA of that branch.
                # If it's a commit SHA, we can't really get "latest" beyond that specific SHA easily for comparison.
                if len(dep['resolved_version']) < 10 and not dep['resolved_version'].startswith('v') and not dep['resolved_version'][0].isdigit(): # Heuristic for branch name
                    latest_version_val = get_latest_commit_sha(dep_owner, dep_repo, dep['resolved_version'], github_token)
                    if latest_version_val:
                        notes = f"Latest commit on branch '{dep['resolved_version']}'."
                    else:
                        notes = f"Could not fetch latest commit for branch '{dep['resolved_version']}'."
                        has_error_fetching_latest = True
                else: # Assume it's a commit SHA
                    latest_version_val = dep['resolved_version'] # Compare SHA to itself
                    notes = "Pinned to specific commit."
            else: # It's likely a version tag
                latest_version_val, version_type, err = get_latest_github_version(dep_owner, dep_repo, github_token)
                has_error_fetching_latest = err
                if latest_version_val:
                    notes = f"Latest from GitHub {version_type}."
                elif not err:
                    notes = "No releases or tags found on GitHub." # Not an error, but no version
                    has_error_fetching_latest = True # Treat as error for status determination
                else:
                    notes = "Error fetching latest version from GitHub."

        status = determine_status_for_resolved(dep['resolved_version'], latest_version_val, dep['is_branch_or_revision'], has_error_fetching_latest)
        
        print(f"  Latest Available: {latest_version_val or 'Unknown'}")
        print(f"  Status: {status}")
        if notes: print(f"    Notes: {notes}")

        final_results.append({
            "name": dep['name'],
            "source_url": dep['url'],
            "resolved_version": dep['resolved_version'],
            "is_branch_or_revision": dep['is_branch_or_revision'],
            "latest_available_version": latest_version_val or "Unknown",
            "status": status,
            "notes": notes.strip()
        })

    # 4. Output results
    output_data = {
        "last_updated_utc": start_time_iso,
        "project_url": PRIMARY_PROJECT_REPO_URL,
        "project_ref_used": PRIMARY_PROJECT_REF or "default branch",
        "package_resolved_path": PACKAGE_RESOLVED_PATH,
        "dependencies": final_results
    }
    
    os.makedirs('docs', exist_ok=True) # Ensure docs directory exists
    output_file = 'docs/project_deps_data.json'
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Dependency check complete!")
        print(f"📄 Results written to {output_file}")
    except IOError as e:
        print(f"\n❌ ERROR: Could not write results to {output_file}: {e}")
        sys.exit(1)

    # Summary
    total = len(final_results)
    up_to_date_count = len([r for r in final_results if "✅" in r['status']])
    updates_available_count = len([r for r in final_results if "⚠️" in r['status']])
    tracking_count = len([r for r in final_results if "ℹ️" in r['status']])
    error_count = len([r for r in final_results if "🚨" in r['status']])

    print(f"\n📊 Summary for dependencies from {PRIMARY_PROJECT_REPO_URL}:")
    print(f"  Total SPM dependencies: {total}")
    print(f"  Up to date: {up_to_date_count}")
    print(f"  Updates available: {updates_available_count}")
    print(f"  Tracking branch/revision: {tracking_count}")
    print(f"  Errors checking: {error_count}")

    if error_count > 0:
        print("\n⚠️ Some dependencies encountered errors during version checking. Review logs.")

if __name__ == "__main__":
    # Example: Ensure you have packaging for better version comparison
    # try:
    #     import packaging
    # except ImportError:
    #     print("INFO: For more accurate version comparison, consider installing the 'packaging' library: pip install packaging")
    main()