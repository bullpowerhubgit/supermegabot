# Git Fetch Extension for VS Code

A VS Code extension that automatically runs git fetch periodically to keep your repositories up to date. Only works on git repositories - automatically detects and filters git-enabled folders.

## Features

- **Smart Git Detection**: Automatically detects git repositories in workspace folders
- **Automatic Git Fetch**: Runs `git fetch --all` periodically only on git repositories
- **Configurable Interval**: Set the fetch interval from 1 minute to 1 hour (default: 5 minutes)
- **Status Bar Indicator**: Shows the current status, repository count, and last fetch time
- **Manual Control**: Start/stop automatic fetching or run fetch manually
- **Multi-workspace Support**: Works with all git repositories in your workspace
- **Notifications**: Optional notifications when fetch completes
- **Error Handling**: Graceful handling of non-git folders and fetch errors
- **Dynamic Workspace**: Automatically adapts when folders are added/removed

## Usage

### Automatic Detection

The extension automatically:

- Scans workspace folders for git repositories
- Only shows the status bar when git repositories are found
- Only runs git fetch on actual git repositories
- Adapts when workspace folders change

### Commands

The extension provides three commands that you can run from the Command Palette (Ctrl+Shift+P / Cmd+Shift+P):

- **Start Git Fetch**: Start the automatic git fetch process
- **Stop Git Fetch**: Stop the automatic git fetch process
- **Manual Git Fetch**: Run git fetch once immediately

### Status Bar

The extension adds a status bar item on the right side that shows:

- `$(sync) Git Fetch` - Extension is ready (no git repos found)
- `$(sync~spin) Git Fetch Running (X repos)` - Automatic fetching is active
- `$(sync) Git Fetch (time) - X repos` - Last fetch completed successfully
- `$(sync) Git Fetch (time) - X✓ Y✗` - Last fetch with errors

Click the status bar item to run a manual git fetch.

## Configuration

You can configure the extension in VS Code settings:

```json
{
  "gitFetchExtension.interval": 300000,        // Fetch interval in milliseconds (default: 5 minutes)
  "gitFetchExtension.enabled": true,           // Enable automatic fetch on startup
  "gitFetchExtension.showNotifications": true  // Show notifications when fetch completes
}
```

## How It Works

1. **Activation**: The extension activates when VS Code: starts
2. **Repository Detection**: Automatically scans workspace folders for git repositories
3. **Smart Filtering**: Only processes folders that contain a `.git` directory and are valid git repositories
4. **Periodic Fetching**: Runs `git fetch --all` at the configured interval only on git repositories
5. **Dynamic Updates**: Re-scans when workspace folders are added or removed
6. **Error Handling**: Gracefully handles network issues and invalid repositories
7. **Status Updates**: Updates the status bar with repository count and results

### Git Repository Detection

The extension uses a two-step verification process:

1. **File System Check**: Looks for `.git` directory in workspace folders
2. **Git Command Verification**: Runs `git status --porcelain` to ensure it's a valid git repository

This ensures that:

- Only actual git repositories are processed
- Non-git folders are completely ignored
- Invalid or corrupted git repositories are skipped
- The extension adapts when folders are added/removed

## Troubleshooting

### Extension Not Working

- Make sure you have git repositories in your workspace
- Check that git is installed and accessible from the command line
- Verify the extension is enabled in VS Code:
- Check the status bar - it should show repository count if git repos are found

### No Git Repositories Detected

- Ensure your workspace folders contain `.git` directories
- Check that git is properly initialized in your repositories
- Try running `git status` manually in your repository folders

### Fetch Errors

- Check your internet connection
- Verify git credentials are configured
- Check repository permissions
- Look for error messages in the VS Code: output panel

### Performance Issues

- Increase the fetch interval if you have many repositories
- Disable notifications if they're too frequent
- The extension only processes git repositories, so performance should be good

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
