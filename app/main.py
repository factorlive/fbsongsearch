from os import getenv
import json
import logging
import uvicorn
import requests
import hashlib
import hmac
from typing import Optional
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import PlainTextResponse
from app.song_handler import song
from app.fbme import fb, fbext
from fbmessenger.elements import Text
from fbmessenger.quick_replies import QuickReply, QuickReplies


#TODO remove
from pprint import pformat

app = FastAPI()

# Logging toolbox 🔊
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

@app.get('/check_queue')
async def check_queue():
    data = {
    }
    pass

@app.get("/webhook")
async def verify_token(
    verify_token: Optional[str] = Query(
        None, alias="hub.verify_token", regex="^[A-Za-z1-9-_]*$"
    ),
    challenge: Optional[str] = Query(
        None, alias="hub.challenge", regex="^[A-Za-z1-9-_]*$"
    ),
    mode: Optional[str] = Query(
        "subscribe", alias="hub.mode", regex="^[A-Za-z1-9-_]*$"
    ),
) -> Optional[str]:
    token = getenv("FB_VERIFY_TOKEN")
    if not token or len(token) < 8:
        logger.error(
            "🔒Token not defined. Must be at least 8 chars or numbers."
            "💡Tip: set -a; source .env; set +a"
        )
        raise HTTPException(status_code=500, detail="Webhook unavailable.")
    elif verify_token == token and mode == "subscribe":
        return PlainTextResponse(f'{challenge}') 
    else:
        raise HTTPException(status_code=403, detail="Token invalid.")


@app.post("/webhook")
async def trigger_response(request: Request) -> None:
    data = await request.json()
    payload = (
        json.dumps(data, separators=(",", ":"))
        .replace("/", "\\/")
        .replace("@", "\\u0040")
        .replace("%", "\\u0025")
        .replace("<", "\\u003C")
        .encode()
    )
    app_secret = getenv("FB_APP_SECRET").encode()
    expected_signature = hmac.new(
        app_secret, payload, digestmod=hashlib.sha1
    ).hexdigest()
    signature = request.headers["x-hub-signature"][5:]
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=403, detail="Message not authenticated.")
    fb.handle(data)
    logger.info(pformat(data, indent=1, depth=10))
    messenger = data['entry'][0]['messaging'][0]
    messenger_meta = list(messenger)
    if 'message' in messenger_meta:
        sender = messenger["sender"]["id"]
        message = messenger["message"]
        message_meta = list(message)
        if 'attachments' in message_meta:
            if message["attachments"][0]["type"] == 'audio':
                audio_url = message['attachments'][0]['payload']['url']
                read_attachment = requests.get(audio_url)
                audioclip_name = fb.check_header(dict(read_attachment.headers))
                if audioclip_name:
                    fbext.save_audio(read_attachment.content, audioclip_name)
                    elem = Text('We will suggest songs soon.')
                    response = fb.send(elem, sender)
                    logger.info(f'Message sent to {sender}. ✅')
                    logger.debug(f'Response after audio was saved: {response}')
                    fbext.remove_audio(audioclip_name)
                # logger.info(fbext.save_audio(audio_url, mp4_name))
                song.log_song(audio_url)
                logger.info(audio_url)
        else:
            # fbext.message(sender, 'Sing or hum a song and I will take a guess.')
            elem = Text('Welcome to the SingSong. Shall we talk or start singing?')
            # response = fb.send(elem.to_dict())
            quick_reply_1 = QuickReply(title="Talk", payload="Let's chit-chat")
            quick_reply_2 = QuickReply(title='Sing', payload="Sing and guess the song!")
            quick_replies = QuickReplies(quick_replies=[quick_reply_1, quick_reply_2])
            text = elem.to_dict()
            text['quick_replies'] = quick_replies.to_dict()
            fb.send(text, 'RESPONSE')
            logger.info(f'Message sent to {sender}. ✅')
            logger.info('this is an attachment')
        logger.info(f'check message {pformat(messenger["message"])}')

    return None


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)
