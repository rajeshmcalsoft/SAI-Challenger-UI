"""sai-challenger-ui: start the UI server.  sai-challenger-ui [--host 127.0.0.1] [--port 8765]"""
import argparse


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sai-challenger-ui", description="SAI Conformance UI server (read-only in this version)")
    ap.add_argument("--host", default="127.0.0.1", help="address to bind (default 127.0.0.1: this machine only)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)

    import uvicorn

    from .api.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
