# 📊 Project Dependency Version Dashboard

An automated dashboard to track iOS project dependency versions by analyzing Package.resolved files.

## Features

- 🔄 Automated weekly version checking via GitHub Actions
- 📊 Clean web dashboard hosted on GitHub Pages
- 🎯 Automatically discovers dependencies from Package.resolved
- 📱 Mobile-friendly responsive design
- 🔍 Tracks both version tags and branch/commit dependencies

## How it Works

1. **Python Script**: `scripts/check_versions2.py` fetches Package.resolved from your project repository
2. **Dependency Discovery**: Automatically parses Swift Package Manager dependencies from Package.resolved
3. **Version Checking**: Compares resolved versions with latest available versions from GitHub
4. **Data File**: Results stored in `docs/data.json`
5. **Dashboard**: `docs/index.html` renders the data in a beautiful responsive interface
6. **Automation**: GitHub Actions runs weekly to update versions

## Configuration

The dependency checker is configured in `scripts/check_versions2.py`:

```python
# Primary project repository to analyze
PRIMARY_PROJECT_REPO_URL = "https://github.com/CongL3/AnniversaryTracker"

# Optional: Specify a branch or commit SHA 
PRIMARY_PROJECT_REF = None  # Uses default branch if None

# Path to Package.resolved within the project repository
PACKAGE_RESOLVED_PATH = "AnniversaryTracker.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"
```

### Common Package.resolved Paths:
- Xcode Project: `YourApp.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved`
- Xcode Workspace: `YourApp.xcworkspace/xcshareddata/swiftpm/Package.resolved`  
- Swift Package: `Package.resolved` (root level)

## Project Structure

```
/
├── docs/
│   ├── index.html         # 📊 Dashboard interface
│   └── data.json          # 🔄 Auto-generated dependency data
├── scripts/
│   ├── check_versions.py    # 📋 Original hardcoded dependency checker
│   └── check_versions2.py   # 🎯 New Package.resolved analyzer
├── .github/workflows/
│   └── update.yml         # ⚙️ GitHub Actions automation
└── README.md              # 📖 This file
```

## Local Development

1. **Clone the repository**
2. **Configure your project**: Update the URLs in `check_versions2.py`
3. **Run the checker**: `python scripts/check_versions2.py`
4. **View dashboard**: Open `docs/index.html` in your browser

## Deployment

1. **Push to GitHub**: Your repository with the configured scripts
2. **Enable GitHub Pages**: Repository Settings → Pages → Deploy from `/docs` folder
3. **Test automation**: Manually trigger the GitHub Action workflow
4. **Access dashboard**: `https://yourusername.github.io/yourrepo`

## Dashboard Features

- 📈 **Real-time Statistics**: Summary cards showing update status
- 🎨 **Status Indicators**: Color-coded status badges for each dependency
- 📱 **Responsive Design**: Works beautifully on mobile devices
- 🔗 **Direct Links**: Click to visit dependency repositories
- ⏱️ **Last Updated**: Shows when data was last refreshed
- 📋 **Project Info**: Displays source project and Package.resolved path

## Dependency Status Types

- ✅ **Up to Date**: Current version matches the latest available
- ⚠️ **Update Available**: A newer version is available
- ℹ️ **Tracks Branch/Revision**: Dependency tracks a specific branch or commit
- 🚨 **Error Checking**: Could not determine latest version

## Privacy & Access

- **Public Repositories**: Works without authentication
- **Private Repositories**: Requires `GITHUB_TOKEN` with appropriate permissions
- **Rate Limits**: GitHub token provides higher API rate limits

## Environment Variables

- `GITHUB_TOKEN`: GitHub Personal Access Token (automatically provided in GitHub Actions)
- `DEBUG_CHECK_VERSIONS`: Set to `true` to enable verbose debugging

## Contributing

To analyze a different project:
1. Update `PRIMARY_PROJECT_REPO_URL` in `check_versions2.py`
2. Update `PACKAGE_RESOLVED_PATH` to match your project structure
3. Commit and push changes - automation will handle the rest! 