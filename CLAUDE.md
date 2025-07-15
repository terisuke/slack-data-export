# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Slack Data Export tool written in Python that exports messages from all accessible Slack channels (public, private, DMs, group messages) and downloads associated files. The exported data is formatted to be compatible with viewers like slack-export-viewer.

## Commands

### Setup and Installation
```bash
# Create virtual environment (if not exists)
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Install dependencies
pip install requests slack-sdk
```

### Running the Application
```bash
# Normal run (starts fresh)
python main.py

# Resume from previous interrupted export
python main.py --resume
```

## Architecture

### Core Components

1. **main.py**: Main application logic that orchestrates the export process
   - Authenticates with Slack API
   - Fetches workspace metadata (users, channels)
   - Exports messages and downloads files
   - Creates ZIP archive of exported data

2. **const.py**: Configuration constants
   - Contains Slack API tokens (USER_TOKEN and BOT_TOKEN)
   - API rate limiting settings (ACCESS_WAIT = 1.2 seconds)
   - Export path configuration
   - Logging and timeout settings

### Data Flow

1. **Authentication**: Uses both User Token and Bot Token for different API operations
2. **Data Collection**: 
   - Fetches user list and channel metadata
   - Iterates through all accessible conversations
   - Downloads message history (with thread support)
   - Downloads associated files with unique prefixes
3. **Export Format**: 
   - Messages saved as JSON files (optionally split by day)
   - File organization matches Slack's official export format
   - Compatible with slack-export-viewer

### Key Implementation Details

- **Rate Limiting**: 
  - Enforced 1.2-second delay between API calls
  - Infinite retry with exponential backoff when rate limited (ensures complete data export)
  - Respects Retry-After headers from Slack API
  - Configurable via MAX_RATE_LIMIT_RETRIES in const.py (0 = infinite)
- **Progress Tracking**: 
  - Saves progress to `.progress_TIMESTAMP.json` files
  - Allows resuming interrupted exports with `--resume` flag
  - Tracks processed channels to avoid re-downloading
- **Error Handling**: 
  - Comprehensive retry logic for rate limit errors (up to 3 retries)
  - Better file download error handling with status code checking
  - Detailed logging for debugging
- **File Downloads**:
  - Improved handling of redirects and authentication
  - Retry logic for failed downloads
  - Better error reporting with HTTP status codes
- **File Naming**: Downloaded files are prefixed with their Slack file ID to ensure uniqueness
- **Token Usage**: USE_USER_TOKEN flag allows switching between user and bot token for different operations
- **Message Splitting**: SPLIT_MESSAGE_FILES option to organize messages by day (like Slack's official export)

## Important Notes

- The `const.py` file contains Slack API tokens that must be configured before use
- Exports are saved to `./export/` directory by default
- Required Slack app scopes: channels:history, channels:read, files:read, groups:history, groups:read, im:history, im:read, mpim:history, mpim:read, users:read

### Rate Limits for Non-Marketplace Apps

As of May 29, 2025, Slack has implemented stricter rate limits for non-Marketplace apps:
- `conversations.history` and `conversations.replies`: 1 request per minute (down from 50+)
- Maximum 15 messages per request (down from 200)

The code automatically detects if it's a non-Marketplace app (`IS_MARKETPLACE_APP = False` in const.py) and:
- Uses 60-second delays between conversation API calls
- Limits requests to 15 messages each
- Implements infinite retry with exponential backoff for rate limit errors

To avoid these restrictions, consider submitting your app to the Slack Marketplace.