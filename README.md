# Slack Data Export

This code exports messages of public channels, private channels, direct
messages and group messages, and downloads files exchanged in those at Slack.

## ⚠️ Important: Slack API Rate Limit Changes (May 29, 2025)

Slack has implemented stricter rate limits for non-Marketplace apps:
- `conversations.history` and `conversations.replies`: **1 request per minute** (down from 50+)
- Maximum **15 messages per request** (down from 200)

This tool automatically adapts to these limits. To avoid restrictions, consider [submitting your app to the Slack Marketplace](https://api.slack.com/start/distributing/guidelines).

## Requirements

- Python 3.6+ (tested with 3.12)
  - "requests" and "slack-sdk" modules
- Slack App's Token
  - https://api.slack.com/apps

A Slack app's token is tied to the required scope.

The required scopes to run this code is as follows:

- `channels:history`, `channels:read`
- `files:read`
- `groups:history`, `groups:read`
- `im:history`, `im:read`
- `mpim:history`, `mpim:read`
- `users:read`

![the required scopes](./docs/images/slack-app-scopes.jpg)

## Usage

Rewrite the `USER_TOKEN` and `BOT_TOKEN` values in const.py to those of your
Slack app:

```python
USER_TOKEN = "xoxp-xxxxxx"  # Your User Token
BOT_TOKEN = "xoxb-xxxxxx"  # Your Bot Token
```

![the tokens](./docs/images/slack-app-tokens.jpg)

Install the external package:

```
$ pip install requests
$ pip install slack-sdk
```

And run main.py:

```
$ python main.py
```

To resume a previously interrupted export:

```
$ python main.py --resume
```

Export messages and files in `EXPORT_BASE_PATH` as a zip file.

### Configuring

List of configuration values in const.py:

| Name                     | Type     | Description                                         |
| ------------------------ | -------- | --------------------------------------------------- |
| ACCESS_WAIT              | float    | Wait time (sec) for general API calls. Default: 2.0 |
| CONVERSATIONS_ACCESS_WAIT| float    | Wait time (sec) for conversations API calls. Default: 60.0 for non-Marketplace apps |
| IS_MARKETPLACE_APP       | boolean  | Whether this is a Marketplace-approved app. Default: False |
| MAX_RATE_LIMIT_RETRIES   | integer  | Maximum retry attempts for rate limits. 0 = infinite. Default: 0 |
| EXPORT_BASE_PATH         | string   | Export directory path. Default: "./export"          |
| LOG_LEVEL                | function | Logging level of the logging module.                |
| REQUESTS_CONNECT_TIMEOUT | float    | Connect timeout (sec) for the requests module.      |
| REQUESTS_READ_TIMEOUT    | float    | Read timeout (sec) for the requests module.         |
| USE_USER_TOKEN           | boolean  | Whether or not to use the User Token.               |
| SPLIT_MESSAGE_FILES      | boolean  | Whether or not to split message files by day.       |

If change `ACCESS_WAIT`, check
[the rate limits](https://api.slack.com/docs/rate-limits) of Slack APIs.

### Features

- **Automatic Rate Limit Handling**: Detects rate limit errors and retries with exponential backoff
- **Progress Tracking**: Saves progress automatically and allows resuming interrupted exports
- **Adaptive Rate Limiting**: Automatically adjusts wait times based on app type (Marketplace vs non-Marketplace)
- **Comprehensive Export**: Exports all accessible messages, threads, and files

### Estimated Export Time

For non-Marketplace apps (with new rate limits):
- 20 channels with ~100 messages each: **5-6 hours**
- 50 channels with ~500 messages each: **25-30 hours**

For Marketplace apps:
- 20 channels with ~100 messages each: **5-10 minutes**
- 50 channels with ~500 messages each: **15-30 minutes**

## Cooperation

By loading the exported zip file into a viewer app such as [@hfaran](https://github.com/hfaran) 's [slack-export-viewer](https://github.com/hfaran/slack-export-viewer), you can view the messages.

![slack-export-viewer](./docs/images/slack-export-viewer.png)

Incidentally, since all conversations are displayed in the public channel column, this script appends "@" to the beginning of the user name in the case of DMs.

## Troubleshooting

### Rate Limit Errors

If you encounter persistent rate limit errors:

1. **Verify your app type**: Set `IS_MARKETPLACE_APP = True` in `const.py` only if your app is approved for the Slack Marketplace
2. **Check your token scopes**: Ensure all required scopes are granted
3. **Consider applying for Marketplace**: This will increase your rate limits from 1 to 50+ requests per minute

### Resume Failed Export

If the export is interrupted:

```bash
# The tool automatically saves progress
# To resume from where it stopped:
$ python main.py --resume
```

### Memory Issues with Large Workspaces

For workspaces with extensive history:
- Consider exporting channels in batches by modifying the channel list
- Increase system swap space if needed
- Monitor disk space as exports can be large

## 日本語での注意事項

2025年5月29日より、Slackは非Marketplaceアプリに対して厳しいレート制限を適用しています：
- conversations.history/replies: 1分あたり1リクエスト（以前は50+）
- 1リクエストあたり最大15メッセージ（以前は200）

本ツールは自動的にこれらの制限に対応しますが、大規模なワークスペースの場合、エクスポートに数時間〜数日かかる可能性があります。より高速なエクスポートを希望する場合は、SlackマーケットプレイスへのApp申請をご検討ください。
