"""
Copy Twitter messages to Telegram
"""
import os
import time
import datetime
import re
import hashlib
import base64
import logging
from dotenv import load_dotenv
import tweepy
import telegram

# settings
CHECK_NEW_TWEETS_IN_LAST_X_DAYS = 30
LIMIT_NEW_TWEETS = 100    # Twitter allow 5-100
TWEET_URL_PATTERN = "https://twitter.com/{user_name}/status/{tweet_id}"

TELEGRAM_CHECK_LAST_POSTS = 20  # search last imported tweet
TELEGRAM_TIMEOUT = 20    # seconds
TELEGRAM_POST_PAUSE = 10    # seconds between posts (too fast -> Telegram don't like it [not faster 20 posts per minute?])

# simpler logger for GitHub Actions and Heroku
if os.getenv("GITHUB_ACTION") or os.getenv("DYNO"):
    logging.basicConfig(format='> %(message)s', level=logging.INFO)
else:
    logging.basicConfig(format='%(asctime)s > %(message)s', level=logging.INFO)

def import_settings():
    """
    check keys in ENV (for GitHub Actions)
    """
    if os.path.exists(".env"):
        load_dotenv(".env")     # it will not overwrite OS ENV


##################################################################
class TwitterClient():
    """
    Twitter Client
    """
    client_api = None
    user_name = None
    user_id = None

    def __init__(self, bearer_token, channel_name):
        """
        https://docs.tweepy.org/en/stable/authentication.html#authentication
        """
        self.client_api = tweepy.Client(bearer_token)

        # https://docs.tweepy.org/en/stable/client.html?highlight=get_user#tweepy.Client.get_user
        self.user_name = channel_name
        user_obj = self.client_api.get_user(username=self.user_name)
        self.user_id = user_obj.data.id
        logging.info("Twitter channel found (%s)", channel_name)


    def get_new_tweet_item(self, tweet, text, attaches):
        """
        Prepare new tweet item from export
        """
        return {
            "id":           tweet.id,
            "created_at":   tweet.created_at,
            "text":         text,
            "attachments":  attaches,
            "tweet_url":    TWEET_URL_PATTERN.format(user_name=self.user_name, tweet_id=tweet.id)
            }

    def normalize_newest_tweets(self, tweets_to_export, tweets_includes):
        """
        Return array of tweets with filtered text
        """
        # collect attachment urls
        media_dic = {}
        if len(tweets_includes) > 0 and len(tweets_includes["media"]) > 0:
            for media in tweets_includes["media"]:
                media_dic[ media.media_key ] = {"url":media.url, "alt":media.alt_text, "type":media.type}

        # collect normalized tweets
        result_list = []
        for tweet in tweets_to_export:
            # replace attachment uids with urls
            exportable_post = True
            tweet_attachments = []
            if tweet.attachments is not None and len(tweet.attachments) > 0:
                for media_key in tweet.attachments["media_keys"]:
                    if media_dic[media_key] is not None:
                        tweet_attachments.append(media_dic[media_key])
                        if media_dic[media_key]["url"] is None:         # No media url => internal media => can't get it's resources => export as tweet url
                            exportable_post = False
                # has poll => can't get it's resources => export as tweet url
                if "poll_ids" in tweet.attachments and len(tweet.attachments["poll_ids"]):
                    exportable_post = False

            # tweets with internal media (twitter's photo or video)
            if exportable_post is False:
                new_tweet_item = self.get_new_tweet_item(tweet, None, [])
                result_list.append( new_tweet_item )
                continue

            # clear text from attachment urls
            tweet_text = tweet.text
            if tweet.entities is not None and "urls" in tweet.entities and len(tweet.entities["urls"]):
                urls2cut = list(filter(lambda x: x["expanded_url"].find("https://twitter.com/") == 0, tweet.entities["urls"]))   # cut only twitter urls!
                urls2cut.sort(key=lambda x: x["start"], reverse=True)   # prepare replaces list in desc order
                for url2cut in urls2cut:
                    if len(tweet_text) > url2cut["start"]:
                        tweet_text = tweet_text[0:url2cut["start"]]+tweet_text[url2cut["end"]:]

            # store normalized tweet
            new_tweet_item = self.get_new_tweet_item(tweet, tweet_text.strip(), tweet_attachments)
            result_list.append( new_tweet_item )

        return result_list


    def get_newest_tweets(self, last_used_tweet_uid_hash):
        """
        Get newest posts, which is after `last_used_uid`
        """
        current_ts = datetime.datetime.utcnow()
        x_days = datetime.timedelta(days = CHECK_NEW_TWEETS_IN_LAST_X_DAYS)
        start_time = (current_ts - x_days).isoformat(timespec="seconds") + "Z"
        # https://docs.tweepy.org/en/stable/client.html#tweepy.Client.get_users_tweets
        latest_tweets = self.client_api.get_users_tweets(
                                                    id=self.user_id,
                                                    expansions=["attachments.media_keys", "attachments.poll_ids"],
                                                    tweet_fields=["id", "text", "attachments", "created_at", "entities"],
                                                    media_fields=["type", "alt_text", "preview_image_url", "url", "duration_ms"],
                                                    poll_fields=["id"],
                                                    start_time=start_time,
                                                    max_results=LIMIT_NEW_TWEETS
                                                    )

        # filter new items only after `last_used_tweet_uid_hash`
        # currently tweets in desc format => search `last_used_tweet_uid_hash` from start
        tweets_to_export = []
        for tweet in latest_tweets.data:
            if TelegramClient.compare_hash_with_id(last_used_tweet_uid_hash, tweet.id):
                break
            tweets_to_export.append(tweet)
        tweets_to_export.reverse()

        result_list = self.normalize_newest_tweets(tweets_to_export, latest_tweets.includes)

        logging.info("Found %s new tweets.", str(len(result_list)))
        return result_list



##################################################################
class TelegramClient():
    """
    Telegram Client
    """
    client_bot = None
    chat_name = None
    chat_id = None
    chat = None

    id_in_descr_pattern = re.compile(r" \[\#\!([-0-9a-zA-Z\._]+)\]$")

    def __init__(self, access_token, channel_name):
        """
        https://python-telegram-bot.readthedocs.io/en/stable/telegram.bot.html
        """
        self.client_bot = telegram.Bot(access_token)
        self.chat_name = channel_name

        # https://python-telegram-bot.readthedocs.io/en/stable/telegram.bot.html#telegram.Bot.get_chat
        self.chat = self.get_chat(self.chat_name)
        self.chat_id = self.chat.id
        logging.info("Telegram chat found (%s)", self.chat_name)

        self.update_id_in_chat_description(0)
        logging.info("Telegram chat description is editable (%s)", self.chat.description)


    def get_chat(self, name):
        """
        Return chat object
        """
        return self.client_bot.get_chat(chat_id="@"+name, timeout=TELEGRAM_TIMEOUT)

    @staticmethod
    def get_hash_of_id(msg_id):
        """
        Return short hash of tweet ID
        Uses additional encoder to compress result
        """
        return base64.urlsafe_b64encode(hashlib.sha256(str(msg_id).encode("utf8")).digest()).decode()[:8]


    @staticmethod
    def compare_hash_with_id(hash_id, check_id):
        """
        Return True if id equal to hash
        In case when Twitter will change its tweet ID format, we just change this function
        """
        return hash_id == TelegramClient.get_hash_of_id(check_id)


    def update_id_in_chat_description(self, msg_id):
        """
        Store last used tweet ID in description of chat
        """
        # remove old number
        new_description = re.sub(self.id_in_descr_pattern, "", self.chat.description)

        # do not update description on Zero if we already has number in description (require only on first run)
        if msg_id == 0 and new_description != self.chat.description:
            return

        id_hash = self.get_hash_of_id(msg_id)
        new_description = new_description + " [#!" + id_hash + "]"

        # https://python-telegram-bot.readthedocs.io/en/stable/telegram.bot.html#telegram.Bot.set_chat_description
        self.client_bot.set_chat_description(chat_id=self.chat_id, description=new_description, timeout=TELEGRAM_TIMEOUT)
        self.chat.description = new_description
        logging.info("Stored last_posted_message_id: [#!%s]", id_hash)


    def get_last_imported_msg_id_hash(self):
        """
        Get last used message ID from telegram channel
        """
        msg_uid = None

        # search last used message ID in channel description
        self.chat = self.get_chat(self.chat_name)   # re-read for better dynamic
        if self.chat.description is not None:
            match = self.id_in_descr_pattern.search(self.chat.description)
            if match is not None:
                msg_uid = match.group(1)

        if msg_uid is None:
            logging.info("Imported messages not found.")
        else:
            logging.info("Last imported message ID = %s", msg_uid)
        return msg_uid


    @staticmethod
    def get_media_by_attachment(attachment, caption):
        """
        Return Media object, based on attachemnt type
        """
        # https://developer.twitter.com/en/docs/twitter-api/data-dictionary/object-model/media
        match attachment["type"]:
            case "photo":
                return telegram.InputMediaPhoto(media=attachment["url"], caption=caption, parse_mode="HTML")
            case "animated_gif":
                return telegram.InputMediaAnimation(media=attachment["url"], caption=caption, parse_mode="HTML")
            case "video":
                return telegram.InputMediaVideo(media=attachment["url"], caption=caption, parse_mode="HTML")
            case "audio":
                return telegram.InputMediaVideo(media=attachment["url"], caption=caption, parse_mode="HTML")
        return None


    def post_new_messages(self, new_messages_list):
        """
        Post new messages
        """
        for message in new_messages_list:
            # get text
            message_text = ""
            if message["text"] is not None:
                message_text = message["text"] + "\n\n"
            elif len(message["attachments"]) == 0:
                message_text = message["tweet_url"]

            # add link to original
            if message_text != message["tweet_url"]:
                message_text = message_text + "[<a href='"+message["tweet_url"]+"'>tweet</a>]"

            # if message exceeds max length of caption => use only link
            if len(message_text.encode('UTF-8')) > 1024:
                message_text = message["tweet_url"]

            # send message
            # https://python-telegram-bot.readthedocs.io/en/stable/telegram.bot.html#telegram.Bot.send_message
            if len(message["attachments"]) == 1:
                attach = message["attachments"][0]
                match attach["type"]:
                    case "photo":
                        self.client_bot.send_photo(chat_id=self.chat_id, photo=attach["url"], caption=message_text, parse_mode="HTML", timeout=TELEGRAM_TIMEOUT)
                    case "animated_gif":
                        self.client_bot.send_animation(chat_id=self.chat_id, animation=attach["url"], caption=message_text, parse_mode="HTML", timeout=TELEGRAM_TIMEOUT)
                    case "video":
                        self.client_bot.send_video(chat_id=self.chat_id, video=attach["url"], caption=message_text, parse_mode="HTML", timeout=TELEGRAM_TIMEOUT)
                    case "audio":
                        self.client_bot.send_audio(chat_id=self.chat_id, audio=attach["url"], caption=message_text, parse_mode="HTML", timeout=TELEGRAM_TIMEOUT)
            elif len(message["attachments"]) > 1:
                media_list = []
                for attach in message["attachments"]:
                    caption = None
                    if len(media_list) == 0:        # groups uses caption of first object
                        caption = message_text
                    media = self.get_media_by_attachment(attach, caption)
                    if media is not None:
                        media_list.append( media )
                self.client_bot.send_media_group(chat_id=self.chat_id, media=media_list, timeout=TELEGRAM_TIMEOUT )
            else:
                self.client_bot.send_message(chat_id=self.chat_id, text=message_text, parse_mode="HTML", timeout=TELEGRAM_TIMEOUT )

            logging.info("Published tweet: %s", message["tweet_url"])
            self.update_id_in_chat_description(message["id"])
            time.sleep(TELEGRAM_POST_PAUSE)



##################################################################
# init
import_settings()
twitter_client = TwitterClient(os.getenv("TWITTER_BEARER"), os.getenv("TWITTER_CHANNEL_NAME"))
telegram_client = TelegramClient(os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHANNEL_NAME"))

def transfer_newest_tweets():
    """
    Transfer newest tweets. Selection by last imported tweet id.
    """
    last_used_post_uid_hash = telegram_client.get_last_imported_msg_id_hash()
    newest_tweets = twitter_client.get_newest_tweets(last_used_post_uid_hash)
    telegram_client.post_new_messages(newest_tweets)

# run transfer if script was executed direcly
if __name__ == "__main__":
    transfer_newest_tweets()
# when script is used as module let user call it where required
