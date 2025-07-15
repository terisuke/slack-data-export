import json
import os
import requests
import shutil
import sys
from datetime import datetime
from logging import basicConfig, getLogger
from time import sleep
import time

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from const import Const

# Initialize logger.
basicConfig(format="%(asctime)s %(name)s:%(lineno)s [%(levelname)s]: " +
            "%(message)s (%(funcName)s)")
logger = getLogger(__name__)
logger.setLevel(Const.LOG_LEVEL)


def retry_on_rate_limit(func, *args, **kwargs):
    """
    Execute a function with automatic retry on rate limit errors.
    
    Args:
        func: The function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        The result of the function call
        
    Raises:
        SlackApiError: For non-rate-limit errors
    """
    retry_count = 0
    while True:
        try:
            return func(*args, **kwargs)
        except SlackApiError as e:
            # Debug logging to understand error structure
            logger.debug(f"SlackApiError caught: {e}")
            logger.debug(f"Error response: {e.response}")
            
            # SlackApiError.response is a dict, not an object with get method
            if isinstance(e.response, dict) and e.response.get('error') == 'ratelimited':
                retry_count += 1
                
                # Try to get retry-after from different possible locations
                retry_after = 60  # Default to 60 seconds
                
                # Check if retry-after is in the response headers (from HTTP response)
                if hasattr(e, 'headers') and e.headers and 'Retry-After' in e.headers:
                    retry_after = int(e.headers['Retry-After'])
                    logger.debug(f"Found Retry-After in headers: {retry_after}")
                # Check if it's in the response body
                elif 'retry_after' in e.response:
                    retry_after = e.response['retry_after']
                    logger.debug(f"Found retry_after in response: {retry_after}")
                
                # Add exponential backoff for repeated retries
                if retry_count > 5:
                    retry_after = min(retry_after * (1.5 ** (retry_count - 5)), 300)  # Exponential growth, cap at 5 minutes
                    logger.info(f"Applying exponential backoff: {retry_after} seconds")
                
                # Check max retry limit if configured
                if Const.MAX_RATE_LIMIT_RETRIES > 0 and retry_count >= Const.MAX_RATE_LIMIT_RETRIES:
                    logger.error(f"Reached maximum retry limit ({Const.MAX_RATE_LIMIT_RETRIES})")
                    raise
                
                # Log appropriate message based on function name
                func_name = func.__name__ if hasattr(func, '__name__') else 'API call'
                logger.warning(f"Rate limited on {func_name}. Waiting {retry_after} seconds (retry #{retry_count})")
                
                time.sleep(retry_after)
            else:
                raise  # Re-raise non-rate-limit errors


def download_file_with_retry(url, headers, timeout):
    """
    Download a file with automatic retry on rate limit or temporary failures.
    
    Args:
        url: The URL to download from
        headers: HTTP headers to send
        timeout: Request timeout tuple (connect, read)
        
    Returns:
        The response object if successful
        
    Raises:
        Exception: For permanent failures
    """
    retry_count = 0
    while True:
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                return response
            elif response.status_code == 429:  # Rate limited
                retry_count += 1
                retry_after = int(response.headers.get('Retry-After', 60))
                
                # Add exponential backoff for repeated retries
                if retry_count > 5:
                    retry_after = min(retry_after * 2, 300)  # Cap at 5 minutes
                
                # Check max retry limit if configured
                if Const.MAX_RATE_LIMIT_RETRIES > 0 and retry_count >= Const.MAX_RATE_LIMIT_RETRIES:
                    logger.error(f"Reached maximum retry limit ({Const.MAX_RATE_LIMIT_RETRIES})")
                    raise Exception(f"Failed to download after {retry_count} retries")
                
                logger.warning(f"File download rate limited. Waiting {retry_after} seconds (retry #{retry_count})")
                time.sleep(retry_after)
            else:
                # For other errors, log details and raise
                logger.error(f"File download failed with status {response.status_code}")
                logger.debug(f"    URL: {url}")
                logger.debug(f"    Headers: {response.headers}")
                
                if len(response.history) > 0:
                    logger.debug(f"    Redirects: {[r.status_code for r in response.history]}")
                    logger.debug(f"    Final URL: {response.url}")
                
                raise Exception(f"HTTP {response.status_code} error")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during file download: {e}")
            retry_count += 1
            
            # For network errors, retry with exponential backoff
            if retry_count > 5:
                wait_time = min(60 * retry_count, 300)  # Cap at 5 minutes
            else:
                wait_time = 10
            
            # Check max retry limit if configured
            if Const.MAX_RATE_LIMIT_RETRIES > 0 and retry_count >= Const.MAX_RATE_LIMIT_RETRIES:
                logger.error(f"Reached maximum retry limit ({Const.MAX_RATE_LIMIT_RETRIES})")
                raise
            
            logger.info(f"Retrying download in {wait_time} seconds (retry #{retry_count})...")
            time.sleep(wait_time)


def main():
    # Check if resuming from previous run
    resume_timestamp = os.environ.get('SLACK_EXPORT_RESUME_TIMESTAMP')
    if resume_timestamp:
        logger.info("---- Resume Slack Data Export ----")
        now = resume_timestamp
    else:
        logger.info("---- Start Slack Data Export ----")
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Export timestamp: {now}")
        # Add initial delay to avoid hitting rate limits immediately
        logger.info("Waiting 10 seconds before starting to avoid rate limits...")
        time.sleep(10)
    
    logger.info(f"Rate limit retry strategy: {'Infinite retries' if Const.MAX_RATE_LIMIT_RETRIES == 0 else f'Max {Const.MAX_RATE_LIMIT_RETRIES} retries'}")
    logger.info(f"App type: {'Marketplace' if Const.IS_MARKETPLACE_APP else 'Non-Marketplace'}")
    if not Const.IS_MARKETPLACE_APP:
        logger.warning("Non-Marketplace app detected. Using reduced rate limits:")
        logger.warning(f"- conversations.history/replies: 1 request/minute (15 messages/request)")
        logger.warning(f"- Wait time: {Const.CONVERSATIONS_ACCESS_WAIT} seconds between requests")
    logger.info(f"General API interval: {Const.ACCESS_WAIT} seconds ({60/Const.ACCESS_WAIT:.1f} requests/minute)")
    
    client = init_webclient()
    
    # Load progress if exists
    progress = load_progress(now)
    
    if not progress.get('users_fetched', False):
        users = get_users(client)
        save_users(users, now)
        save_progress(now, {'users_fetched': True})
    else:
        users = load_users(now)
        logger.info("Loaded users from previous run")
    
    if not progress.get('channels_fetched', False):
        channels = get_accessible_channels(client, users)
        save_channels(channels, now)
        save_progress(now, {'users_fetched': True, 'channels_fetched': True})
    else:
        channels = load_channels(now)
        logger.info("Loaded channels from previous run")

    processed_channels = progress.get('processed_channels', [])
    
    for channel in channels:
        if channel["id"] in processed_channels:
            logger.info(f"Skipping already processed channel: {channel['name']}")
            continue
            
        try:
            messages = get_messages(client, channel["id"])
            messages = sort_messages(messages)
            save_messages(messages, channel["name"], now)
            save_files(messages, channel["name"], now)
            
            # Update progress after successful processing
            processed_channels.append(channel["id"])
            save_progress(now, {
                'users_fetched': True,
                'channels_fetched': True,
                'processed_channels': processed_channels
            })
            
        except Exception as e:
            logger.error(f"Error processing channel {channel['name']}: {e}")
            logger.info("Progress saved. You can resume from this point.")
            raise

    archive_data(now)
    
    # Clean up progress file after successful completion
    cleanup_progress(now)

    logger.info("---- End Slack Data Export ----")

    return None


def init_webclient():
    client = None

    if Const.USE_USER_TOKEN:
        logger.info("Use USER TOKEN")
        client = WebClient(token=Const.USER_TOKEN)
    else:
        logger.info("Use BOT TOKEN")
        client = WebClient(token=Const.BOT_TOKEN)

    return client


def get_users(client):
    users = []

    try:
        logger.debug("Call users_list (Slack API)")
        response = retry_on_rate_limit(client.users_list)
        users = response["members"]
        sleep(Const.ACCESS_WAIT)

    except SlackApiError as e:
        logger.error(f"Failed to get users: {e}")
        raise

    return users


def get_accessible_channels(client, users):
    channels = []
    channels_raw = []
    cursor = None

    try:
        while True:
            logger.debug("Call conversations_list (Slack API)")
            conversations_list = retry_on_rate_limit(
                client.conversations_list,
                types="public_channel,private_channel,mpim,im",
                cursor=cursor,
                limit=200
            )
            
            channels_raw.extend(conversations_list["channels"])
            sleep(Const.ACCESS_WAIT)

            cursor = fetch_next_cursor(conversations_list)
            if not cursor:
                break
            else:
                logger.debug("  next cursor: " + cursor)

        # In the case a im (Direct Messages), "name" dose't exist in "channel",
        # so takes and appends "real_name" from users_list as "name".
        # And append "@" to the beginning of "name" in the case a im, to
        # distinguish from channel names.
        channels = [{
            **x,
            **{
                "name":
                "@" + [y for y in users if y["id"] == x["user"]][0]["real_name"]
            }
        } if x["is_im"] else x for x in channels_raw]

    except SlackApiError as e:
        # Only log errors that weren't already handled by retry logic
        if e.response.get('error') != 'ratelimited':
            logger.error(e)
        raise  # Re-raise to properly handle the error

    return channels


def ensure_export_directory(now):
    """Ensure the export directory exists"""
    export_path = os.path.join(Const.EXPORT_BASE_PATH, now)
    os.makedirs(export_path, exist_ok=True)
    return export_path


def save_users(users, now):
    export_path = ensure_export_directory(now)

    logger.info("Save Users")
    logger.debug("users export path : " + export_path)

    file_path = os.path.join(export_path, "users.json")
    with open(file_path, mode="wt", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

    return None


def save_channels(channels, now):
    export_path = ensure_export_directory(now)

    logger.info("Save Channels")
    logger.debug("channels export path : " + export_path)

    file_path = os.path.join(export_path, "channels.json")
    with open(file_path, mode="wt", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

    return None


def get_messages(client, channel_id):
    messages = []
    cursor = None

    try:
        logger.info("Get Messages of " + channel_id)

        # Stores channel's messages (other than thread's).
        while True:
            logger.debug("Call conversations_history (Slack API)")
            # Use reduced limit for non-Marketplace apps
            limit_value = 15 if not Const.IS_MARKETPLACE_APP else 200
            conversations_history = retry_on_rate_limit(
                client.conversations_history,
                channel=channel_id,
                cursor=cursor,
                limit=limit_value
            )
            
            messages.extend(conversations_history["messages"])
            # Use longer wait time for conversations methods if not Marketplace app
            wait_time = Const.CONVERSATIONS_ACCESS_WAIT if not Const.IS_MARKETPLACE_APP else Const.ACCESS_WAIT
            logger.debug(f"Waiting {wait_time} seconds before next conversations API call")
            sleep(wait_time)

            cursor = fetch_next_cursor(conversations_history)
            if not cursor:
                break
            else:
                logger.debug("  next cursor: " + cursor)

        # Stores thread's messages.
        # Extracts messages whose has "thread_ts" is equal to "ts".
        for parent_message in (
                x for x in messages
                if "thread_ts" in x and x["thread_ts"] == x["ts"]):

            cursor = None  # Reset cursor for each thread
            while True:
                logger.debug("Call conversations_replies (Slack API): " +
                             parent_message["ts"])
                # Use reduced limit for non-Marketplace apps
                limit_value = 15 if not Const.IS_MARKETPLACE_APP else 200
                conversations_replies = retry_on_rate_limit(
                    client.conversations_replies,
                    channel=channel_id,
                    ts=parent_message["thread_ts"],
                    cursor=cursor,
                    limit=limit_value
                )
                
                # Since parent messages are also returned, excepts them.
                messages.extend([
                    x for x in conversations_replies["messages"]
                    if x["ts"] != x["thread_ts"]
                ])
                # Use longer wait time for conversations methods if not Marketplace app
                wait_time = Const.CONVERSATIONS_ACCESS_WAIT if not Const.IS_MARKETPLACE_APP else Const.ACCESS_WAIT
                logger.debug(f"Waiting {wait_time} seconds before next conversations API call")
                sleep(wait_time)

                cursor = fetch_next_cursor(conversations_replies)  # Fixed: was using conversations_history
                if not cursor:
                    break
                else:
                    logger.debug("  next cursor: " + cursor)

    except SlackApiError as e:
        # Only log errors that weren't already handled by retry logic
        if e.response.get('error') != 'ratelimited':
            logger.error(e)
        raise  # Re-raise to properly handle the error in main()

    return messages


def fetch_next_cursor(api_response):
    if ("response_metadata" in api_response
            and "next_cursor" in api_response["response_metadata"]
            and api_response["response_metadata"]["next_cursor"]):

        return api_response["response_metadata"]["next_cursor"]
    else:
        return None


def sort_messages(org_messages):
    sort_messages = sorted(org_messages, key=lambda x: x["ts"])
    return sort_messages


def save_messages(messages, channel_name, now):
    export_path = os.path.join(Const.EXPORT_BASE_PATH, now, channel_name)
    os.makedirs(export_path, exist_ok=True)

    logger.info("Save Messages of " + channel_name)
    logger.debug("messages export path : " + export_path)

    if Const.SPLIT_MESSAGE_FILES:
        # Get a list of timestamps (Format YY-MM-DD) by excluding duplicate
        # timestamps in messages.
        for day_ts in {
                format_ts(x["ts"]): format_ts(x["ts"])
                for x in messages
        }.values():
            # Extract messages of "day_ts".
            day_messages = [
                x for x in messages if format_ts(x["ts"]) == day_ts
            ]

            file_path = os.path.join(export_path, f"{day_ts}.json")
            with open(file_path, mode="wt", encoding="utf-8") as f:
                json.dump(day_messages, f, ensure_ascii=False, indent=2)
    else:
        file_path = os.path.join(export_path, "messages.json")
        with open(file_path, mode="wt", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    return None


def format_ts(unix_time_str):
    return datetime.fromtimestamp(float(unix_time_str)).strftime("%Y-%m-%d")


def save_files(messages, channel_name, now):
    export_path = os.path.join(Const.EXPORT_BASE_PATH, now, channel_name, "files")
    os.makedirs(export_path, exist_ok=True)

    logger.info("Save Files of " + channel_name)
    logger.debug("files export path : " + export_path)

    token = Const.USER_TOKEN if Const.USE_USER_TOKEN else Const.BOT_TOKEN

    for files in (x["files"] for x in messages if "files" in x):
        # Downloads files except deleted.
        for fi in (x for x in files if x["mode"] != "tombstone"):
            logger.debug("  * Download " + fi["name"])

            try:
                response = download_file_with_retry(
                    fi["url_private"],
                    headers={"Authorization": "Bearer " + token},
                    timeout=(Const.REQUESTS_CONNECT_TIMEOUT,
                             Const.REQUESTS_READ_TIMEOUT)
                )
                
                file_path = os.path.join(export_path, f"{fi['id']}_{fi['name']}")
                with open(file_path, mode="wb") as f:
                    f.write(response.content)
                logger.debug(f"    Successfully downloaded {fi['name']}")
                
            except Exception as e:
                logger.error(f"Failed to download {fi['name']}: {e}")
                logger.error(f"URL: {fi['url_private']}")
            
            sleep(Const.ACCESS_WAIT)

    return None


def archive_data(now):
    root_path = os.path.join(Const.EXPORT_BASE_PATH, now)

    logger.info("Archive data")

    shutil.make_archive(root_path, format='zip', root_dir=root_path)
    shutil.rmtree(root_path)

    return None


def save_progress(now, progress_data):
    """Save progress to a JSON file for resume capability"""
    progress_path = os.path.join(Const.EXPORT_BASE_PATH, f".progress_{now}.json")
    with open(progress_path, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, ensure_ascii=False, indent=2)


def load_progress(now):
    """Load progress from a previous run if it exists"""
    progress_path = os.path.join(Const.EXPORT_BASE_PATH, f".progress_{now}.json")
    if os.path.exists(progress_path):
        with open(progress_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # Check for any recent progress files
    progress_files = [f for f in os.listdir(Const.EXPORT_BASE_PATH) if f.startswith('.progress_')]
    if progress_files:
        # Sort by modification time and get the most recent
        progress_files.sort(key=lambda x: os.path.getmtime(os.path.join(Const.EXPORT_BASE_PATH, x)), reverse=True)
        most_recent = progress_files[0]
        logger.info(f"Found previous progress file: {most_recent}")
        logger.info("Use --resume flag or rename the progress file to match current timestamp to resume")
    
    return {}


def cleanup_progress(now):
    """Remove progress file after successful completion"""
    progress_path = os.path.join(Const.EXPORT_BASE_PATH, f".progress_{now}.json")
    if os.path.exists(progress_path):
        os.remove(progress_path)
        logger.info("Progress file cleaned up")


def load_users(now):
    """Load users from previously saved file"""
    file_path = os.path.join(Const.EXPORT_BASE_PATH, now, "users.json")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Users file not found: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_channels(now):
    """Load channels from previously saved file"""
    file_path = os.path.join(Const.EXPORT_BASE_PATH, now, "channels.json")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Channels file not found: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--resume':
        # Find the most recent progress file
        progress_files = [f for f in os.listdir(Const.EXPORT_BASE_PATH) if f.startswith('.progress_')]
        if progress_files:
            progress_files.sort(key=lambda x: os.path.getmtime(os.path.join(Const.EXPORT_BASE_PATH, x)), reverse=True)
            # Extract timestamp from filename
            timestamp = progress_files[0].replace('.progress_', '').replace('.json', '')
            logger.info(f"Resuming export from {timestamp}")
            # Set resume mode with existing timestamp
            os.environ['SLACK_EXPORT_RESUME_TIMESTAMP'] = timestamp
        else:
            logger.error("No progress file found to resume from.")
            sys.exit(1)
    
    main()
