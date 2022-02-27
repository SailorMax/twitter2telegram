# Twitter to Telegram

Transfer tweets from one Twitter channel to Telegram chat

## Peculiarities
- work via Twitter API v2 (Essential mode)
- work via Telegram Bot API
- standalone solution

## Warning
After start usage do not delete `[#!n82an48]`-like ID from target Telegram chat description! By this ID the script track last imported tweet. If you remove it, import starts "from begin" (100 last tweets).

## Guide
1. Get Twitter API Bearer Token from [here](https://developer.twitter.com/)
2. Go to [@BotFather](https://t.me/botfather) in Telegram and create a Bot to get `Access Token`
3. Setup to Bot for target channel next permissions: `Change channel info` and `Post messages`
4. Create and fill `.env` based on `.env.skel` (for local use) OR copy it's variables to `Settings/Secrets/Actions` (GitHub) or `Config Vars` (Heroku)
5. For local use run the script by executing:
```sh
$ pip3 install -r requirements.txt
$ python3 twitter2telegram.py
# or `python3 repeater.py 60` to make transfer each 60 minutes
```

## Deploying to Heroku
```sh
$ heroku create
$ git push heroku main
$ heroku open
```
or

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)
