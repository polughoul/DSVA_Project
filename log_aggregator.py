#!/usr/bin/env python3
import argparse
import logging
import logging.handlers
import pickle
import socketserver
import struct
from pathlib import Path


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            header = self.connection.recv(4)
            if len(header) < 4:
                break
            frame_length = struct.unpack(">L", header)[0]
            payload = self.connection.recv(frame_length)
            while len(payload) < frame_length:
                payload += self.connection.recv(frame_length - len(payload))

            record = logging.makeLogRecord(pickle.loads(payload))
            logger = logging.getLogger(record.name)
            logger.handle(record)


class ThreadedLogServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host: str, port: int, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(output_path, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

    with ThreadedLogServer((host, port), LogRecordStreamHandler) as server:
        logging.getLogger("aggregator").info(
            "Log aggregator listening on %s:%s (output=%s)",
            host,
            port,
            output_path
        )
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Centralize node logs")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=9020, help="Bind port")
    parser.add_argument(
        "--output",
        default="logs/aggregated.log",
        help="Output log file"
    )
    args = parser.parse_args()

    serve(args.host, args.port, Path(args.output))


if __name__ == "__main__":
    main()
