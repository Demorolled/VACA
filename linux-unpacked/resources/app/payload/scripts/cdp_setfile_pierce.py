#!/usr/bin/env python3
"""Pierce into the Colab notebook's sandboxed output iframes and set files on
the upload widget's <input type=file> via CDP DOM.setFileInputFiles.

Usage: python3 scripts/cdp_setfile_pierce.py <local_file>
"""
import json
import sys
import urllib.request

import websocket

path = sys.argv[1]

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next((t for t in tabs if t.get("type") == "page" and "colab" in t.get("url", "")), None)
if page is None:
    print("NO COLAB TAB")
    sys.exit(1)
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
mid = [0]


def call(method, params=None):
    mid[0] += 1
    m = mid[0]
    ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == m:
            return msg


def find_file_inputs(node, depth=0, max_depth=12):
    """Recursively walk the DOM (piercing iframe content_documents) for file inputs."""
    found = []
    node_id = node.get("nodeId")
    if node.get("nodeName") == "INPUT":
        attrs = node.get("attributes") or []
        attrs = {attrs[i]: attrs[i + 1] for i in range(0, len(attrs) - 1, 2)}
        if attrs.get("type") == "file":
            found.append(node_id)
    children = node.get("children") or []
    for ch in children:
        found += find_file_inputs(ch, depth + 1, max_depth)
    # pierce into iframe frame owners
    frame_id = node.get("frameId")
    cd = node.get("contentDocument")
    if cd and cd.get("nodeId"):
        found += find_file_inputs(cd, depth + 1, max_depth)
    return found


doc = call("DOM.getDocument", {"depth": 2, "pierce": True})
root = doc["result"]["root"]
targets = find_file_inputs(root)
if not targets:
    # retry with a deeper dive
    doc = call("DOM.getDocument", {"depth": -1, "pierce": True})
    root = doc["result"]["root"]
    targets = find_file_inputs(root)

if not targets:
    print("NO FILE INPUT FOUND in any frame")
    ws.close()
    sys.exit(1)

node_id = targets[0]
r = call("DOM.setFileInputFiles", {"nodeId": node_id, "files": [path]})
print("files set on node", node_id, "| error:", r.get("error", "none"))
ws.close()
sys.exit(0)
