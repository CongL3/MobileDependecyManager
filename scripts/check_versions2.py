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
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError, URLError
import re
import base64 # For decoding GitHub file content
import http.cookiejar # For GitHub raw file access with token

# --- Configuration ---
PRIMARY_PROJECT_REPO_URL = "https://github.com/CongL3/AnniversaryTracker"
# Optional: Specify a branch or commit SHA for the primary project.
# If None, it will try to use the default branch of the project repo.
PRIMARY_PROJECT_REF = "main" # Explicitly set, can be None to use default

# Path to Package.resolved within the project repository.
PACKAGE_RESOLVED_PATH = "AnniversaryTracker.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"

# Set to True to enable verbose debugging output
DEBUG_MODE = os.environ.get('DEBUG_CHECK_VERSIONS', 'False').lower() == 'true'
REQUEST_TIMEOUT = 20

# --- Helper Functions ---

def log_debug(message: str):
    if DEBUG_MODE:
        print(f"DEBUG: {message}")

def parse_github_url_to_owner_repo(url: str) -> Tuple[Optional[str], Optional[str]]:
    if not url:
        return None, None
    processed_url = url.removesuffix('.git').rstrip('/')
    pattern = r'^(?:https?|git)://github\.com/([^/]+)/([^/]+)$'
    match = re.match(pattern, processed_url)
    if match:
        owner, repo = match.group(1), match.group(2)
        log_debug(f"Parsed URL '{url}' -> Owner: '{owner}', Repo: '{repo}'")
        return owner, repo
    log_debug(f"Failed to parse GitHub URL to owner/repo: '{url}'")
    return None, None

def make_api_request(url: str, token: Optional[str] = None, is_raw_download: bool = False) -> Optional[Any]:
    headers = {'User-Agent': 'Project-Dependency-Checker/1.0'}
    if token:
        headers['Authorization'] = f'token {token}'
        log_debug(f"Using GITHUB_TOKEN for request to {url}")
    else:
        log_debug(f"No GITHUB_TOKEN found for request to {url}. Rate limits/access may be restricted.")

    if is_raw_download:
        cookie_jar = http.cookiejar.CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookie_jar))
        if token: opener.addheaders = [('Authorization', f'token {token}')]
    else:
        headers['Accept'] = 'application/vnd.github.v3+json'
        opener = build_opener()

    opener.addheaders = list(headers.items())
    log_debug(f"Making GET request to: {url} with headers: {headers if DEBUG_MODE else '...'}")

    try:
        request = Request(url)
        with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
            log_debug(f"Response status {response.status} for {url}")
            if response.status == 200:
                content = response.read()
                return content if is_raw_download else json.loads(content.decode('utf-8'))
            else:
                print(f"WARN: HTTP {response.status} for {url}. Body: {response.read().decode('utf-8', errors='ignore')[:200]}")
                return None
    except HTTPError as e:
        error_body = ""
        try: error_body = e.read().decode('utf-8', errors='ignore')
        except Exception: pass
        print(f"ERROR: HTTP Error {e.code} for {url}: {e.reason}. Response body: {error_body[:500]}")
        if e.code == 403 and "rate limit exceeded" in error_body.lower(): print("ERROR: GitHub API rate limit exceeded.")
        elif e.code == 401 and token: print("ERROR: GitHub Token might be invalid or lack permissions.")
        return None
    except URLError as e: print(f"ERROR: URL Error for {url}: {e.reason}"); return None
    except json.JSONDecodeError as e: print(f"ERROR: Failed to decode JSON from {url}: {e}"); return None
    except Exception as e: print(f"ERROR: Unexpected error for {url}: {type(e).__name__} - {e}"); return None

def get_file_content_from_github(owner: str, repo: str, file_path: str, ref: Optional[str], token: Optional[str]) -> Optional[str]:
    ref_param = f"?ref={ref}" if ref else ""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}{ref_param}"
    log_debug(f"Fetching file content from GitHub API: {api_url}")
    
    data = make_api_request(api_url, token)
    if data and 'content' in data and data.get('encoding') == 'base64':
        try: return base64.b64decode(data['content']).decode('utf-8')
        except Exception as e: print(f"ERROR: Failed to decode base64 content for '{file_path}': {e}"); return None
    elif data and 'download_url' in data and data['download_url']:
        log_debug(f"Trying download_url: {data['download_url']}")
        raw_bytes = make_api_request(data['download_url'], token, is_raw_download=True)
        if raw_bytes:
            try: return raw_bytes.decode('utf-8')
            except UnicodeDecodeError as e: print(f"ERROR: Failed to decode from download_url for '{file_path}': {e}"); return None
    elif data: print(f"ERROR: Unexpected response for file content of '{file_path}'. Keys: {list(data.keys())}")
    else: print(f"ERROR: Failed to fetch file content for '{file_path}' from {owner}/{repo} at ref '{ref}'.")
    return None

def parse_package_resolved(content: str) -> List[Dict[str, Any]]:
    dependencies = []
    try:
        data = json.loads(content)
        version_format = data.get("version", 1)

        pins = []
        if version_format == 1:
            pins = data.get("object", {}).get("pins", [])
        elif version_format == 2:
            pins = data.get("pins", [])
        else:
            print(f"ERROR: Unsupported Package.resolved version_format: {version_format}")
            return []

        for pin in pins:
            state = pin.get("state", {})
            package_identity = ""
            repo_url = ""

            if version_format == 1:
                package_identity = pin.get("package", pin.get("identity"))
                repo_url = pin.get("repositoryURL")
            elif version_format == 2:
                package_identity = pin.get("identity")
                repo_url = pin.get("location")
            
            if not package_identity and repo_url:
                 package_identity = os.path.basename(repo_url.removesuffix(".git"))
            if not package_identity or not repo_url:
                log_debug(f"Skipping pin due to missing identity or URL: {pin}")
                continue

            resolved_version_tag = state.get("version")
            resolved_branch_name = state.get("branch")
            resolved_revision_sha = state.get("revision")

            current_pin_value: str
            # This new key clearly defines how the pin should be treated for version checking
            pin_type: str # "version", "branch", "revision", "unknown"

            if resolved_version_tag:
                current_pin_value = resolved_version_tag
                pin_type = "version"
            elif resolved_branch_name:
                current_pin_value = resolved_branch_name
                pin_type = "branch"
            elif resolved_revision_sha:
                current_pin_value = resolved_revision_sha
                pin_type = "revision"
            else:
                log_debug(f"Pin for {package_identity} has no version, branch, or revision in state: {state}")
                current_pin_value = "unknown_state"
                pin_type = "unknown"
            
            dependencies.append({
                "name": package_identity,
                "url": repo_url,
                "resolved_value": current_pin_value, # Renamed from resolved_version for clarity
                "pin_type": pin_type 
            })
            
        log_debug(f"Parsed {len(dependencies)} dependencies from Package.resolved (format v{version_format})")
        return dependencies
    except json.JSONDecodeError as e: print(f"ERROR: Failed to parse Package.resolved JSON: {e}"); return []
    except Exception as e: print(f"ERROR: Unexpected error parsing Package.resolved: {e}"); return []

def get_latest_github_version(owner: str, repo: str, token: Optional[str]) -> Tuple[Optional[str], str, bool]:
    release_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    release_data = make_api_request(release_url, token)
    if release_data and 'tag_name' in release_data:
        log_debug(f"Latest release for {owner}/{repo}: {release_data['tag_name']}")
        return release_data['tag_name'], "release", False

    tags_url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    tags_data = make_api_request(tags_url, token)
    if tags_data and isinstance(tags_data, list) and len(tags_data) > 0:
        latest_tag_name = tags_data[0].get('name')
        if latest_tag_name:
            log_debug(f"Latest tag for {owner}/{repo}: {latest_tag_name}")
            return latest_tag_name, "tag", False
            
    log_debug(f"Could not find releases or tags for {owner}/{repo}")
    return None, "unknown", True

def get_latest_commit_sha(owner: str, repo: str, branch_name: str, token: Optional[str]) -> Optional[str]:
    branch_url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch_name}"
    branch_data = make_api_request(branch_url, token)
    if branch_data and 'commit' in branch_data and 'sha' in branch_data['commit']:
        sha = branch_data['commit']['sha']
        log_debug(f"Latest commit SHA for {owner}/{repo} on branch '{branch_name}': {sha[:7]}")
        return sha[:7]
    log_debug(f"Could not get commit SHA for {owner}/{repo} on branch '{branch_name}'.")
    return None

def determine_status(
    resolved_val: str, 
    latest_available_val: Optional[str], 
    pin_type_val: str, 
    has_error_fetching: bool
) -> str:
    if has_error_fetching or latest_available_val is None:
        return "🚨 Error Checking"
    
    if pin_type_val == "branch":
        # resolved_val is branch name, latest_available_val is its latest SHA
        # To accurately say "Up to Date", we'd need the Package.resolved's specific commit SHA for this branch.
        # For now, just indicate it's tracking.
        return f"ℹ️ Tracks Branch"
    
    if pin_type_val == "revision":
        # resolved_val is a commit SHA. If latest_available_val is also this SHA (or not applicable for comparison)
        if resolved_val.startswith(latest_available_val): # Compare SHAs
            return "✅ Up to Date (Revision)"
        return f"ℹ️ Pinned to Revision" # Or "⚠️ Diverged from Pin" if different

    # If pin_type_val is "version" (or unknown and we assume version)
    if pin_type_val == "version" or pin_type_val == "unknown":
        norm_resolved = resolved_val.lstrip('vV')
        norm_latest = latest_available_val.lstrip('vV')

        if norm_resolved == norm_latest:
            return "✅ Up to Date"
        
        try:
            from packaging.version import parse as parse_version
            parsed_resolved = parse_version(norm_resolved)
            parsed_latest = parse_version(norm_latest)

            if parsed_resolved < parsed_latest:
                return "⚠️ Update Available"
            elif parsed_resolved > parsed_latest:
                return "✅ Up to Date (Newer)" 
            else: # Equal
                return "✅ Up to Date"
        except ImportError:
            log_debug("`packaging` library not found. Using string comparison.")
            if norm_resolved < norm_latest: return "⚠️ Update Available"
        except Exception as e: 
            log_debug(f"Could not semantically compare '{norm_resolved}' and '{norm_latest}': {e}. Using string comparison.")
            if norm_resolved < norm_latest: return "⚠️ Update Available"
        
        return "✅ Up to Date" # Default if comparisons lead here

    return "❓ Unknown Status" # Fallback for unhandled pin_type

# --- Main Logic ---
def main():
    start_time_iso = datetime.now(timezone.utc).isoformat()
    print(f"🔍 Project Dependency Checker (SPM from Package.resolved)")
    print(f"📅 Started at: {start_time_iso}")
    print(f"🎯 Primary Project Repo: {PRIMARY_PROJECT_REPO_URL}")
    if PRIMARY_PROJECT_REF: print(f"🌲 Using Ref/Branch: {PRIMARY_PROJECT_REF}")
    print(f"📄 Package.resolved Path: {PACKAGE_RESOLVED_PATH}")
    if DEBUG_MODE: print("--- DEBUG MODE ENABLED ---")

    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token: print("⚠️ WARNING: GITHUB_TOKEN not set. Rate limits low, private repos inaccessible.")

    project_owner, project_repo = parse_github_url_to_owner_repo(PRIMARY_PROJECT_REPO_URL)
    if not project_owner or not project_repo:
        print(f"❌ ERROR: Could not parse primary project URL: {PRIMARY_PROJECT_REPO_URL}"); sys.exit(1)

    package_resolved_content = get_file_content_from_github(
        project_owner, project_repo, PACKAGE_RESOLVED_PATH, PRIMARY_PROJECT_REF, github_token
    )
    if not package_resolved_content:
        print(f"❌ ERROR: Failed to fetch Package.resolved from '{PRIMARY_PROJECT_REPO_URL}' at '{PACKAGE_RESOLVED_PATH}'."); sys.exit(1)

    resolved_deps = parse_package_resolved(package_resolved_content)
    if not resolved_deps:
        print("ℹ️ No dependencies found/parsed in Package.resolved.")
        output_data = {"last_updated_utc": start_time_iso, "project_url": PRIMARY_PROJECT_REPO_URL, "dependencies": []}
        os.makedirs('docs', exist_ok=True)
        with open('docs/data.json', 'w', encoding='utf-8') as f: json.dump(output_data, f, indent=2, ensure_ascii=False)
        print("📄 Empty results written to docs/data.json"); sys.exit(0)
    
    print(f"\n🔎 Found {len(resolved_deps)} dependencies. Checking latest versions...")

    final_results = []
    for dep in resolved_deps: # dep now has 'resolved_value' and 'pin_type'
        print(f"\nChecking: {dep['name']} ({dep['url']})")
        print(f"  Resolved: {dep['resolved_value']} (Type: {dep['pin_type']})")

        dep_owner, dep_repo_name = parse_github_url_to_owner_repo(dep['url'])
        latest_val: Optional[str] = None
        notes = ""
        has_error = False

        if not dep_owner or not dep_repo_name:
            notes = "Could not parse dependency GitHub URL."
            has_error = True
        else:
            if dep['pin_type'] == "version":
                latest_val, version_type, err = get_latest_github_version(dep_owner, dep_repo_name, github_token)
                has_error = err
                if latest_val: notes = f"Latest from GitHub {version_type}."
                elif not err: notes = "No releases or tags found on GitHub."; has_error = True # Treat as error if expecting version
                else: notes = "Error fetching latest version from GitHub."
            
            elif dep['pin_type'] == "branch":
                # dep['resolved_value'] is the branch name
                latest_val = get_latest_commit_sha(dep_owner, dep_repo_name, dep['resolved_value'], github_token)
                if latest_val: notes = f"Latest commit on branch '{dep['resolved_value']}'."
                else: notes = f"Could not fetch latest commit for branch '{dep['resolved_value']}'."; has_error = True
            
            elif dep['pin_type'] == "revision":
                # dep['resolved_value'] is a commit SHA.
                latest_val = dep['resolved_value'] # The "latest" for a pinned SHA is itself.
                notes = "Pinned to specific commit."
            
            elif dep['pin_type'] == "unknown":
                notes = "Unknown pin state in Package.resolved."
                has_error = True
            
        status = determine_status(dep['resolved_value'], latest_val, dep['pin_type'], has_error)
        
        print(f"  Latest Available: {latest_val or 'Unknown'}")
        print(f"  Status: {status}")
        if notes: print(f"    Notes: {notes}")

        final_results.append({
            "name": dep['name'],
            "source_url": dep['url'],
            "resolved_value": dep['resolved_value'],
            "pin_type": dep['pin_type'].capitalize(),
            "latest_available_version": latest_val or "Unknown",
            "status": status,
            "notes": notes.strip()
        })

    output_data = {
        "last_updated_utc": start_time_iso,
        "project_url": PRIMARY_PROJECT_REPO_URL,
        "project_ref_used": PRIMARY_PROJECT_REF or "default branch",
        "package_resolved_path": PACKAGE_RESOLVED_PATH,
        "dependencies": final_results
    }
    
    os.makedirs('docs', exist_ok=True)
    output_file = 'docs/data.json' # Changed from project_deps_data.json to match TDD for index.html
    try:
        with open(output_file, 'w', encoding='utf-8') as f: json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Dependency check complete!")
        print(f"📄 Results written to {output_file}")
    except IOError as e: print(f"\n❌ ERROR: Could not write to {output_file}: {e}"); sys.exit(1)

    total = len(final_results)
    up_to_date_count = len([r for r in final_results if "✅ Up to Date" in r['status']]) # More specific check
    updates_available_count = len([r for r in final_results if "⚠️" in r['status']])
    tracking_count = len([r for r in final_results if "ℹ️" in r['status']])
    error_count = len([r for r in final_results if "🚨" in r['status']])

    print(f"\n📊 Summary for dependencies from {PRIMARY_PROJECT_REPO_URL}:")
    print(f"  Total SPM dependencies: {total}")
    print(f"  Up to date: {up_to_date_count}")
    print(f"  Updates available: {updates_available_count}")
    print(f"  Tracking/Pinned: {tracking_count}") # Combined category
    print(f"  Errors checking: {error_count}")

    if error_count > 0: print("\n⚠️ Some dependencies encountered errors. Review logs.")

if __name__ == "__main__":
    # Optional: Check for 'packaging' library
    try:
        import packaging
    except ImportError:
        print("INFO: For more accurate version comparison, consider installing the 'packaging' library: pip install packaging")
    main()