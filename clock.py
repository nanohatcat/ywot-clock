import asyncio
import websockets
import json
import time
import datetime
import argparse
import pyfiglet

FONT = 'future' # pyfiglet font
FORCE_FULL_SYNC_INTERVAL = 30  # how often you want it to regen (paste in as if it's ran for the first time)

def get_ideal_map(target_date, start_x, start_y):
    now = datetime.datetime.now()
    diff = target_date - now
    # Format: d hh:mm:ss
    display_text = f"{diff.days}D\n{diff.seconds//3600:02d}:{(diff.seconds%3600)//60:02d}:{diff.seconds%60:02d}"

    fig = pyfiglet.Figlet(font=FONT)
    lines = fig.renderText(display_text).splitlines()
    ideal_map = {}
    for r, line in enumerate(lines):
        for c, char in enumerate(line):
            ideal_map[(start_x + c, start_y + r)] = char
    return ideal_map

async def listen_for_changes(ws, observed_map):
    try:
        async for message in ws:
            try:
                data = json.loads(message)
                if data.get("kind") == "write":
                    for edit in data.get("edits", []):
                        abs_x = (edit[1] * 16) + edit[3]
                        abs_y = (edit[0] * 8) + edit[2]
                        # update our local map of the world
                        # note: i have no idea if this works
                        observed_map[(abs_x, abs_y)] = edit[5]
            except: pass
    except: pass

async def watch_and_repair(ws, target_date, start_x, start_y, observed_map):
    last_full_sync = 0

    while True:
        ideal_map = get_ideal_map(target_date, start_x, start_y)
        edits = []
        timestamp = int(time.time() * 1000)

        # check if it's time to force a full overwrite
        is_full_sync = (time.time() - last_full_sync) > FORCE_FULL_SYNC_INTERVAL

        for coord, char in ideal_map.items():
            # if doing a full sync, we treat current as "None" to force a match
            current = None if is_full_sync else observed_map.get(coord)

            if current != char:
                wx, wy = coord
                # [tile_y, tile_x, char_y, char_x, timestamp, char, edit_index]
                edits.append([wy // 8, wx // 16, wy % 8, wx % 16, timestamp, char, len(edits) + 1])
                observed_map[coord] = char

        if edits:
            if is_full_sync:
                print(f"rewriting all ({len(edits)} tiles)")
                last_full_sync = time.time()
            # else:
            #     print(f"repairing {len(edits)} tiles...")
            # why is this here?

            # batching is often more reliable than just sending all the edits at once (that can rate limit you)
            for i in range(0, len(edits), 50):
                payload = {"kind": "write", "request_id": 1, "edits": edits[i:i+50]}
                await ws.send(json.dumps(payload))
                await asyncio.sleep(0.3)

        await asyncio.sleep(0.5)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", type=str, default="")
    parser.add_argument("--x", type=int, default=0)
    parser.add_argument("--y", type=int, default=0)
    args = parser.parse_args()

    url = f'wss://www.yourworldoftext.com/{args.page.strip("/")}/ws/' if args.page else 'wss://www.yourworldoftext.com/ws/' # you can use owot for this i'm pretty sure
    target_date = datetime.datetime(2027, 1, 1, 0, 0, 0) # the time you want. (yyyy/mm/dd/hh/mm/ss)

    observed_map = {}

    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                print("connected and watchdog up")
                # we start the listener
                listener = asyncio.create_task(listen_for_changes(ws, observed_map))
                await watch_and_repair(ws, target_date, args.x, args.y, observed_map)
        except Exception as e:
            print(f"connection lost, error: {e}. retrying...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
