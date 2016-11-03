# ws://localhost:5672

import asyncio
import aiohttp
import websockets
import json
import pprint


#connecting steps
REQUEST_CONNECT = 0
SEND_CODE = 1
AUTH_READBACK = 2

#milton actions
PLAY_SONG = 0
STOP_PLAYING = 1

send_queue = asyncio.Queue()

#queue
tracks = {}
track_lock = asyncio.Lock()

#current track
current_track = None
current_track_lock = asyncio.Lock()


pp = pprint.PrettyPrinter(indent=1)

async def build_tracks(queue):
    with await track_lock:
        global tracks
        tracks = {}
        for t in queue:
            tracks[t["title"]] = t
        print("Track list updated")

async def set_current_track(trk):
    with await current_track_lock:
        print("Current track set")
        global current_track
        current_track = trk
        
async def on_play_state(play_state):
    print("on play state "  + str(play_state))
    if play_state:
        with await current_track_lock, await track_lock:
            global current_track
            global tracks
            if current_track is not None:
                pp.pprint(current_track)
                current_title = current_track["title"]
                id = "dne"
                track = None
                if current_title in tracks:
                    pp.pprint(tracks[current_title])
                    track = tracks[current_title]
                    id = track["id"]
                else:
                    raise Exception("Track not in queue")
                print("SEND PLAY " + id + " TO SERVER")
                b = {}
                b["id"] = id
                b["action"] = "play"
                b["title"] = track["title"]
                b["artist"] = track["artist"]
                b["duration"] = track["duration"]
                with aiohttp.ClientSession() as session:
                    await session.post("http://127.0.0.1:8080", data=json.dumps(b))
    else:
        print("SEND STOP PLAY TO SERVER")
            

async def consumer(message):
    m = json.loads(message)
    #connect channel
    if "channel" not in m:
        print("channel is none, message is :")
        pp.pprint(m)
    elif m["channel"] == "connect":
        print("Consumer: " + str(message))
        if m["payload"] == "CODE_REQUIRED":
            ui_code = input("Enter code")
            print("UI_CODE from consumer: " + str(ui_code))
            await send_queue.put((SEND_CODE, ui_code))
        else:
            auth_hash = m["payload"]
            await send_queue.put((AUTH_READBACK, auth_hash))
    elif m["channel"] == "track":
        await set_current_track(m["payload"])
    elif m["channel"] == "playState":
        await on_play_state(m["payload"])
    elif m["channel"] == "queue":
        await build_tracks(m["payload"])
        
        
async def producer():
    message = {}
    message["namespace"] = "connect"
    message["method"] = "connect"
    task = await send_queue.get()
    if task[0] == REQUEST_CONNECT:
        message["arguments"] = ["WS Test"]
    elif task[0] == SEND_CODE:
        print("UI_CODE: from producer" + str(ui_code))
        message["arguments"] = ["WS Test", task[1]]
    elif task[0] == AUTH_READBACK:
        message["arguments"] = ["WS Test", task[1]]
    
    print("Sending message:")
    pp.pprint(message)
    send_queue.task_done()
    return json.dumps(message)
        
async def server_controller(command):
    action = command[0]
    data = command[1]
    
    if action == PLAY_SONG:
        print("send http request to play " + data)
        
async def handler(websocket):
    while True:
        message = await websocket.recv()
        await consumer(message)

async def startup():
    #await send_queue.put((REQUEST_CONNECT, 0))
    async with websockets.connect('ws://localhost:5672') as ws:   
        await handler(ws)
        
asyncio.get_event_loop().run_until_complete(startup())