# 📊 Dependency Version Dashboard

An automated dashboard to track iOS and Android dependency versions across projects.

## Features

- 🔄 Automated weekly version checking via GitHub Actions
- 📊 Clean web dashboard hosted on GitHub Pages
- 🎯 Tracks both Swift Package Manager and Gradle dependencies
- 📱 Mobile-friendly responsive design

## How it Works

1. **Python Script**: `scripts/check_versions.py` fetches latest versions from GitHub API
2. **Data File**: Results stored in `docs/data.json`
3. **Dashboard**: `docs/index.html` renders the data in a clean table
4. **Automation**: GitHub Actions runs weekly to update versions

## Dependencies Currently Tracked

### iOS (Swift Package Manager)
- AlertToast
- Firebase 
- Lottie
- Mantis
- Reachability
- SDWebImageSwiftUI
- GoogleMobileAds
- GoogleUserMessagingPlatform
- swiftui-introspect
- TOCropViewController

### Android (Gradle)
Coming in future iteration.

## Local Development

1. Clone the repository
2. Run the version checker: `python scripts/check_versions.py`
3. Open `docs/index.html` in your browser

## Dashboard

Visit the live dashboard at: `https://your-username.github.io/your-repo-name`

## Contributing

To add a new dependency, update the dependency list in `scripts/check_versions.py` and the script will automatically track it. 