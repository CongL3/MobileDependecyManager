#!/usr/bin/env python3
"""
Dependency Version Checker

This script checks the latest versions of iOS and Android dependencies
by querying GitHub repositories and outputs the results to docs/data.json.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import re

# List of iOS dependencies to track
IOS_DEPENDENCIES = [
    {
        "name": "AlertToast",
        "url": "https://github.com/elai950/AlertToast",
        "current": "1.3.9"
    },
    {
        "name": "Firebase",
        "url": "https://github.com/firebase/firebase-ios-sdk.git",
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
        "url": "https://github.com/googleads/swift-package-manager-user-messaging",
        "current": "2.1.0"
    },
    {
        "name": "swiftui-introspect",
        "url": "https://github.com/siteline/SwiftUI-Introspect.git",
        "current": "0.2.3"
    },
    {
        "name": "TOCropViewController",
        "url": "https://github.com/TimOliver/TOCropViewController",
        "current": "2.6.1"
    }
]


def parse_github_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse GitHub URL to extract owner and repository name.
    
    Args:
        url: GitHub repository URL
        
    Returns:
        Tuple of (owner, repo) or (None, None) if parsing fails
    """
    # Remove .git suffix if present (properly, not as character set)
    if url.endswith('.git'):
        url = url[:-4]
    
    # Match github.com URLs - capture everything after the second slash until end or special chars
    pattern = r'github\.com[:/]([^/]+)/([^/?#\s]+)'
    match = re.search(pattern, url)
    
    if match:
        owner = match.group(1)
        repo = match.group(2)
        # Additional cleanup
        repo = repo.rstrip('/')
        return owner, repo
    
    return None, None


def make_github_request(url: str) -> Optional[Dict]:
    """
    Make a request to GitHub API with proper headers and error handling.
    
    Args:
        url: GitHub API URL
        
    Returns:
        JSON response as dict or None if request fails
    """
    headers = {
        'User-Agent': 'Dependency-Version-Checker/1.0',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Add GitHub token if available for higher rate limits
    github_token = os.environ.get('GITHUB_TOKEN')
    if github_token:
        headers['Authorization'] = f'token {github_token}'
    
    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=10) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
            else:
                print(f"HTTP {response.status} for {url}")
                return None
    except HTTPError as e:
        print(f"HTTP Error {e.code} for {url}: {e.reason}")
        return None
    except URLError as e:
        print(f"URL Error for {url}: {e.reason}")
        return None
    except Exception as e:
        print(f"Unexpected error for {url}: {e}")
        return None


def get_latest_release(owner: str, repo: str) -> Optional[str]:
    """
    Get the latest release tag for a GitHub repository.
    
    Args:
        owner: Repository owner
        repo: Repository name
        
    Returns:
        Latest release tag or None if not found
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    data = make_github_request(url)
    
    if data and 'tag_name' in data:
        return data['tag_name']
    
    return None


def get_latest_tag(owner: str, repo: str) -> Optional[str]:
    """
    Get the latest tag for a GitHub repository (fallback if no releases).
    
    Args:
        owner: Repository owner
        repo: Repository name
        
    Returns:
        Latest tag or None if not found
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    data = make_github_request(url)
    
    if data and isinstance(data, list) and len(data) > 0:
        return data[0]['name']
    
    return None


def get_latest_commit_sha(owner: str, repo: str, branch: str = "master") -> Optional[str]:
    """
    Get the latest commit SHA for a specific branch.
    
    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch name (default: master)
        
    Returns:
        Latest commit SHA (short) or None if not found
    """
    # Try the specified branch first
    url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"
    data = make_github_request(url)
    
    if data and 'commit' in data and 'sha' in data['commit']:
        return data['commit']['sha'][:7]  # Return short SHA
    
    # If master fails, try main
    if branch == "master":
        url = f"https://api.github.com/repos/{owner}/{repo}/branches/main"
        data = make_github_request(url)
        
        if data and 'commit' in data and 'sha' in data['commit']:
            return data['commit']['sha'][:7]
    
    return None


def determine_status(current: str, latest: str, tracks_branch: bool, has_error: bool) -> str:
    """
    Determine the status based on current vs latest version.
    
    Args:
        current: Current version
        latest: Latest version
        tracks_branch: Whether this dependency tracks a branch
        has_error: Whether there was an error checking this dependency
        
    Returns:
        Status string with emoji
    """
    if has_error:
        return "🚨 Error Checking"
    
    if tracks_branch:
        return "ℹ️ Tracks Branch"
    
    if current == latest:
        return "✅ Up to Date"
    
    return "⚠️ Update Available"


def check_dependency_version(dependency: Dict) -> Dict:
    """
    Check the version status of a single dependency.
    
    Args:
        dependency: Dictionary containing name, url, and current version
        
    Returns:
        Dictionary with version information and status
    """
    name = dependency['name']
    url = dependency['url']
    current = dependency['current']
    
    print(f"Checking {name}...")
    
    # Parse GitHub URL
    owner, repo = parse_github_url(url)
    
    if not owner or not repo:
        return {
            "name": name,
            "url": url,
            "current": current,
            "latest": "Unknown",
            "status": "🚨 Error Checking",
            "notes": "Could not parse GitHub URL"
        }
    
    # Check if current version is a branch name
    tracks_branch = current in ['master', 'main', 'develop', 'dev']
    
    if tracks_branch:
        # Get latest commit SHA for branch
        latest = get_latest_commit_sha(owner, repo, current)
        notes = f"Tracking {current} branch"
    else:
        # Get latest release
        latest = get_latest_release(owner, repo)
        
        # Fallback to latest tag if no releases
        if not latest:
            latest = get_latest_tag(owner, repo)
        
        notes = ""
    
    has_error = latest is None
    if has_error:
        latest = "Unknown"
        notes = "Could not fetch latest version"
    
    status = determine_status(current, latest, tracks_branch, has_error)
    
    result = {
        "name": name,
        "url": url,
        "current": current,
        "latest": latest,
        "status": status
    }
    
    if notes:
        result["notes"] = notes
    
    return result


def main():
    """Main function to check all dependencies and generate data.json."""
    print("🔍 Checking dependency versions...")
    print(f"📅 Started at: {datetime.now().isoformat()}")
    
    # Check all dependencies
    results = []
    for dependency in IOS_DEPENDENCIES:
        result = check_dependency_version(dependency)
        results.append(result)
        
        # Print status
        status_symbol = result['status'].split()[0]
        print(f"  {status_symbol} {result['name']}: {result['current']} → {result['latest']}")
    
    # Create output data
    output_data = {
        "last_updated": datetime.now().isoformat(),
        "dependencies": results
    }
    
    # Ensure docs directory exists
    os.makedirs('docs', exist_ok=True)
    
    # Write to docs/data.json
    output_file = 'docs/data.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Version check complete!")
    print(f"📄 Results written to {output_file}")
    
    # Summary statistics
    total = len(results)
    up_to_date = len([r for r in results if "✅" in r['status']])
    updates_available = len([r for r in results if "⚠️" in r['status']])
    tracking_branch = len([r for r in results if "ℹ️" in r['status']])
    errors = len([r for r in results if "🚨" in r['status']])
    
    print(f"\n📊 Summary:")
    print(f"  Total dependencies: {total}")
    print(f"  Up to date: {up_to_date}")
    print(f"  Updates available: {updates_available}")
    print(f"  Tracking branches: {tracking_branch}")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    main() 