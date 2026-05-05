#!/usr/bin/env python3
"""TCP port forwarder for developer portal access.

Forwards Mac host requests through the tooling container to the
service containers on the Docker bridge network.

Usage: python3 port-forward.py
"""

import asyncio


FORWARDS = {
    8000: ("172.21.0.10", 8000),  # service-api (Org1/Issuer)
    8001: ("172.20.0.10", 8000),  # stablecoin-switch (Org3/Switch)
}

BUFFER_SIZE = 65536


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while data := await reader.read(BUFFER_SIZE):
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _handle(local_reader: asyncio.StreamReader, local_writer: asyncio.StreamWriter,
                  remote_host: str, remote_port: int):
    try:
        remote_reader, remote_writer = await asyncio.open_connection(remote_host, remote_port)
    except (ConnectionRefusedError, OSError):
        local_writer.close()
        return
    await asyncio.gather(
        _copy(local_reader, remote_writer),
        _copy(remote_reader, local_writer),
    )


async def _server(listen_port: int, remote_host: str, remote_port: int):
    async def on_connect(reader, writer):
        await _handle(reader, writer, remote_host, remote_port)

    server = await asyncio.start_server(on_connect, "0.0.0.0", listen_port)
    print(f"Forwarding 0.0.0.0:{listen_port} -> {remote_host}:{remote_port}")
    async with server:
        await server.serve_forever()


async def main():
    servers = []
    for listen_port, (remote_host, remote_port) in FORWARDS.items():
        servers.append(asyncio.create_task(_server(listen_port, remote_host, remote_port)))
    print(f"Portal forwarder running ({len(servers)} ports)")
    await asyncio.gather(*servers)


if __name__ == "__main__":
    asyncio.run(main())