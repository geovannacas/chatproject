# server.py
import asyncio
import json
import struct
import base64
import uuid
from datetime import datetime

# In-memory maps (basic). For scaling você usaria Redis/shared state.
USERS = {}      # username -> writer
GROUPS = {}     # group_name -> set(usernames)
OFFLINE_MESSAGES = {}  # username -> [msg...]

# framing helpers
async def read_message(reader: asyncio.StreamReader):
    header = await reader.readexactly(4)
    length = struct.unpack(">I", header)[0]
    data = await reader.readexactly(length)
    return json.loads(data.decode())

async def send_message(writer: asyncio.StreamWriter, obj):
    data = json.dumps(obj).encode()
    writer.write(struct.pack(">I", len(data)))
    writer.write(data)
    await writer.drain()

async def handle_client(reader, writer):
    peer = writer.get_extra_info("peername")
    username = None
    try:
        # first message should be auth
        msg = await read_message(reader)
        if msg.get("type") != "auth" or "username" not in msg:
            await send_message(writer, {"type":"error","reason":"auth required"})
            writer.close()
            await writer.wait_closed()
            return

        username = msg["username"]
        if username in USERS:
            await send_message(writer, {"type":"error","reason":"username_taken"})
            writer.close()
            await writer.wait_closed()
            return

        USERS[username] = writer
        print(f"{username} connected from {peer}")
        # deliver any offline messages
        queue = OFFLINE_MESSAGES.pop(username, [])
        for m in queue:
            await send_message(writer, m)

        # event loop for client messages
        while True:
            msg = await read_message(reader)
            mtype = msg.get("type")
            if mtype == "private":
                to = msg.get("to")
                msg_record = {"type":"private","from":username,"to":to,"text":msg.get("text"),"ts":datetime.utcnow().isoformat()}
                if to in USERS:
                    await send_message(USERS[to], msg_record)
                    await send_message(writer, {"type":"ack","for":msg_record})
                else:
                    # store offline
                    OFFLINE_MESSAGES.setdefault(to, []).append(msg_record)
                    await send_message(writer, {"type":"info","msg":"recipient_offline_stored"})
            elif mtype == "create_group":
                g = msg.get("group")
                members = set(msg.get("members", []))
                members.add(username)
                GROUPS[g] = members
                await send_message(writer, {"type":"info","msg":f"group {g} created"})
            elif mtype == "group":
                g = msg.get("group")
                if g not in GROUPS:
                    await send_message(writer, {"type":"error","reason":"no_such_group"})
                    continue
                msg_record = {"type":"group","from":username,"group":g,"text":msg.get("text"),"ts":datetime.utcnow().isoformat()}
                for member in GROUPS[g]:
                    if member == username: continue
                    if member in USERS:
                        await send_message(USERS[member], msg_record)
                    else:
                        OFFLINE_MESSAGES.setdefault(member, []).append(msg_record)
            elif mtype == "file_init":
                # forward to recipient(s) the metadata
                to = msg.get("to")
                file_id = msg.get("file_id") or str(uuid.uuid4())
                msg_meta = {"type":"file_init","from":username,"to":to,"filename":msg.get("filename"),"filesize":msg.get("filesize"),"file_id":file_id}
                if to in USERS:
                    await send_message(USERS[to], msg_meta)
                else:
                    OFFLINE_MESSAGES.setdefault(to, []).append(msg_meta)
                await send_message(writer, {"type":"info","msg":"file_init_received","file_id":file_id})
            elif mtype == "file_chunk":
                to = msg.get("to")
                # simply forward chunk
                if to in USERS:
                    await send_message(USERS[to], msg)
                else:
                    OFFLINE_MESSAGES.setdefault(to, []).append(msg)
            elif mtype == "quit":
                break
            else:
                await send_message(writer, {"type":"error","reason":"unknown_type"})
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        if username:
            USERS.pop(username, None)
            print(f"{username} disconnected")
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

async def main(host='192.168.5.35', port=5000):
    server = await asyncio.start_server(handle_client, host, port)
    addr = server.sockets[0].getsockname()
    print(f"Serving on {addr}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
