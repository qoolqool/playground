#!/usr/bin/env python3
"""
Persistent embedding daemon — loads sentence-transformers once, serves
embeddings via Unix socket. Avoids Ollama HTTP overhead and model reload cost.
Expects ~40ms per embed instead of ~330ms.

Protocol: connect, send text line (UTF-8, max 512 chars), receive JSON line.
"""
import json
import os
import sys
import socket
import threading
from sentence_transformers import SentenceTransformer

SOCKET_PATH = "/tmp/embed-server.sock"
MODEL_NAME = "BAAI/bge-small-en-v1.5"


def handle(client: socket.socket, model: SentenceTransformer):
    try:
        data = client.recv(8192)
        if data:
            text = data.decode("utf-8").strip()[:512]
            embedding = model.encode(text).tolist()
            response = json.dumps({"embedding": embedding, "dim": len(embedding)})
            client.sendall((response + "\n").encode("utf-8"))
    except Exception as e:
        err = json.dumps({"error": str(e)}) + "\n"
        client.sendall(err.encode("utf-8"))
    finally:
        client.close()


def main():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    print(f"[embed-server] Loading model {MODEL_NAME}...", file=sys.stderr, flush=True)
    model = SentenceTransformer(MODEL_NAME)
    print(f"[embed-server] Model loaded, listening on {SOCKET_PATH}", file=sys.stderr, flush=True)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)
    server.listen(8)

    while True:
        client, _ = server.accept()
        t = threading.Thread(target=handle, args=(client, model), daemon=True)
        t.start()


if __name__ == "__main__":
    main()
