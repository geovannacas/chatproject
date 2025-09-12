# client.py
import asyncio
import json
import struct
import base64
import os
import uuid
import sys

async def read_message(reader):
    header = await reader.readexactly(4)
    length = struct.unpack(">I", header)[0]
    data = await reader.readexactly(length)
    return json.loads(data.decode())

async def send_message(writer, obj):
    data = json.dumps(obj).encode()
    writer.write(struct.pack(">I", len(data)))
    writer.write(data)
    await writer.drain()

async def interactive(host='192.168.5.35', port=5000, username=None):
    reader, writer = await asyncio.open_connection(host, port)
    if not username:
        username = input("Nome de usuário: ").strip()
    await send_message(writer, {"type":"auth","username":username})

    async def reader_task():
        try:
            while True:
                msg = await read_message(reader)
                print("<<<", msg)
                if msg.get("type") == "file_init":
                    print("incoming file:", msg.get("filename"), "from", msg.get("from"))
                if msg.get("type") == "file_chunk":
                    # append/assemble
                    fid = msg["file_id"]
                    data = base64.b64decode(msg["data"])
                    with open(f"recv_{fid}", "ab") as f:
                        f.write(data)
        except Exception as e:
            print("connection closed", e)
            return

    asyncio.create_task(reader_task())

    # CLI loop
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if line.startswith("/pm "):
            _, to, *rest = line.split()
            text = " ".join(rest)
            await send_message(writer, {"type":"private","to":to,"text":text})
        elif line.startswith("/group "):
            _, group, *rest = line.split()
            text = " ".join(rest)
            await send_message(writer, {"type":"group","group":group,"text":text})
        elif line.startswith("/create "):
            _, g, members = line.split(maxsplit=2)
            member_list = members.split(",")
            await send_message(writer, {"type":"create_group","group":g,"members":member_list})
        elif line.startswith("/sendfile "):
            _, to, path = line.split(maxsplit=2)
            if not os.path.exists(path):
                print("file not found")
                continue
            fid = str(uuid.uuid4())
            filesize = os.path.getsize(path)
            await send_message(writer, {"type":"file_init","to":to,"filename":os.path.basename(path),"filesize":filesize,"file_id":fid})
            # send chunks
            with open(path,"rb") as f:
                idx = 0
                while True:
                    chunk = f.read(32*1024)  # 32KB
                    if not chunk:
                        break
                    await send_message(writer, {"type":"file_chunk","to":to,"file_id":fid,"chunk_index":idx,"data":base64.b64encode(chunk).decode()})
                    idx += 1
            await send_message(writer, {"type":"file_end","to":to,"file_id":fid})
            print("file sent.")
        elif line == "/quit":
            await send_message(writer, {"type":"quit"})
            writer.close()
            await writer.wait_closed()
            break
        else:
            print("comandos: /pm <user> <msg>, /group <group> <msg>, /create <group> <user1,user2>, /sendfile <user> <path>, /quit")

if __name__ == "__main__":
    import sys
    username = sys.argv[1] if len(sys.argv)>1 else None
    asyncio.run(interactive(username=username))
