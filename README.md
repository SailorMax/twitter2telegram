# Tweeter to Telegram

Transfer tweets from one Tweeter channel to Telegram chat

## Peculiarities
- work via Twitter API v2 (Essential mode)
- work via Telegram Bot API
- standalone solution (last transfered tweet id store in chat description)

## Guide
1. Get Twitter API Bearer Token from [here](https://developer.twitter.com/)
2. Go to [@BotFather](https://t.me/botfather) in telegram and create a Bot to get `Access Token`
3. Setup to Bot for target channel `Change channel info` and `Post messages` permissions
4. Create and fill `.env` based on `.env.skel` (for local) OR copy it's variables to "`Environment secrets`"/"`Config Vars`" (GitHub Actions, Heroku,..)
5. Run the script by executing:
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
