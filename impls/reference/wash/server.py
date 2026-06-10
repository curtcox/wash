"""HTTP server entry point for the reference wash runtime."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from wash.executor import (
    ExecutionError,
    PipelineResult,
    execute_pipeline,
    execute_raw_command,
    load_exec_rules,
)
from wash.filesystem import (
    EnvConfigError,
    RootEscapeError,
    SymlinkEscapeError,
    delete_file,
    directory_listing,
    find_index_file,
    infer_mime,
    infer_mime_from_bytes,
    listing_enabled,
    literal_path_parts_from_raw,
    load_index_names,
    put_file,
    read_file_bytes,
    split_raw_target,
)
from wash.metadata import head_permitted
from wash.parser import (
    FilesystemParse,
    NotFoundParse,
    ParseError,
    PipelineParse,
    RawCommandParse,
    check_methods,
    load_command_path,
    parse_request,
)

MAX_ERROR_BODY = 8192
BIND_HOST = "127.0.0.1"


class WashHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, server_address: tuple[str, int], handler_cls: type, config: ServerConfig
    ) -> None:
        super().__init__(server_address, handler_cls)
        self.config = config


class ServerConfig:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.command_dirs = load_command_path(self.root)
        self.exec_config = load_exec_rules(self.root)


class WashRequestHandler(BaseHTTPRequestHandler):
    server: WashHTTPServer  # type: ignore[assignment]

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _raw_target(self) -> str:
        target = self.path
        if not target:
            return "/"
        return target.split("#", 1)[0]

    def _request_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _accepts_json(self) -> bool:
        accept = self.headers.get("Accept", "")
        return "application/json" in accept and "text/plain" not in accept.split(",")[0]

    def _error_body(
        self,
        status: int,
        message: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> bytes:
        extra = extra or {}
        if self._accepts_json():
            payload = {"status": status, "error": message, **extra}
            body = json.dumps(payload, indent=2).encode("utf-8")
        else:
            lines = [message]
            for key, value in extra.items():
                lines.append(f"{key}: {value}")
            body = "\n".join(lines).encode("utf-8")
            if not body.endswith(b"\n"):
                body += b"\n"
        if len(body) > MAX_ERROR_BODY:
            truncated = body[: MAX_ERROR_BODY - 32]
            suffix = b"\n... [truncated]\n"
            body = truncated + suffix
        return body

    def _send_response(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain",
        extra_headers: dict[str, str] | None = None,
        omit_body: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(0 if omit_body else len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if not omit_body and self.command != "HEAD":
            self.wfile.write(body)

    def _send_error(
        self,
        status: int,
        message: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        body = self._error_body(status, message, extra=extra)
        self._send_response(status, body, content_type="text/plain; charset=utf-8")

    def _pipeline_headers(self, result: PipelineResult) -> dict[str, str]:
        headers: dict[str, str] = {}
        if result.final_command:
            headers["X-WebShell-Command"] = result.final_command
        if result.pipeline_description:
            headers["X-WebShell-Pipeline"] = result.pipeline_description
        if result.source_path:
            headers["X-WebShell-Source"] = str(
                self.server.config.root / result.source_path
            )
        return headers

    def _handle_filesystem_get(self, resource: FilesystemParse) -> None:
        root = self.server.config.root
        path = resource.resource.path
        omit_body = self.command == "HEAD"
        try:
            if resource.resource.kind == "file":
                data = read_file_bytes(path)
                self._send_response(
                    200,
                    data,
                    content_type=infer_mime(path, root),
                    omit_body=omit_body,
                )
                return

            index = find_index_file(path, load_index_names(root))
            if index is not None:
                data = read_file_bytes(index)
                self._send_response(
                    200,
                    data,
                    content_type=infer_mime(index, root),
                    omit_body=omit_body,
                )
                return

            if not listing_enabled(root):
                self._send_error(404, "not found")
                return
        except EnvConfigError as exc:
            self._send_error(500, str(exc))
            return

        listing = directory_listing(path)
        self._send_response(
            200,
            listing,
            content_type="text/plain; charset=utf-8",
            omit_body=omit_body,
        )

    def _handle_put_delete_literal(self, method: str, raw_target: str) -> None:
        segments = split_raw_target(raw_target.split("?", 1)[0])
        try:
            parts = literal_path_parts_from_raw(segments)
        except Exception:
            self._send_error(400, "invalid path")
            return

        if method == "PUT":
            body = self._request_body()
            try:
                put_file(
                    self.server.config.root,
                    parts,
                    body,
                    create_parents=True,
                )
            except (RootEscapeError, SymlinkEscapeError):
                self._send_error(403, "path not permitted")
                return
            except FileNotFoundError:
                self._send_error(404, "parent directory not found")
                return
            except OSError as exc:
                self._send_error(500, f"write failed: {exc}")
                return
            self._send_response(200, b"", content_type="text/plain; charset=utf-8")
            return

        if method == "DELETE":
            try:
                delete_file(self.server.config.root, parts)
            except (RootEscapeError, SymlinkEscapeError):
                self._send_error(403, "path not permitted")
                return
            except FileNotFoundError:
                self._send_error(404, "file not found")
                return
            except OSError as exc:
                self._send_error(500, f"delete failed: {exc}")
                return
            self._send_response(200, b"", content_type="text/plain; charset=utf-8")
            return

    def _handle_command(
        self,
        parsed: PipelineParse | RawCommandParse,
        *,
        body: bytes,
    ) -> None:
        config = self.server.config
        method = self.command
        if method == "HEAD":
            if isinstance(parsed, PipelineParse):
                check_methods(parsed.stages, method)
            else:
                check_methods([parsed.stage], method)
            method = "GET"

        try:
            if isinstance(parsed, RawCommandParse):
                check_methods([parsed.stage], self.command)
                result = execute_raw_command(
                    parsed,
                    root=config.root,
                    command_dirs=config.command_dirs,
                    exec_config=config.exec_config,
                    method=method,
                    body=body,
                )
            else:
                check_methods(parsed.stages, self.command)
                result = execute_pipeline(
                    parsed,
                    root=config.root,
                    command_dirs=config.command_dirs,
                    exec_config=config.exec_config,
                    body=body,
                )
        except ParseError as exc:
            self._send_error(exc.status, exc.message)
            return
        except ExecutionError as exc:
            self._send_error(exc.status, exc.message)
            return

        if result.http_status >= 400:
            fail = result.failing_stage
            extra: dict[str, Any] = {
                "pipeline": result.pipeline_description,
            }
            if fail:
                extra["command"] = fail.name
                extra["exit_status"] = fail.exit_code
                if fail.stdout:
                    extra["stdout"] = fail.stdout.decode("utf-8", errors="replace")[
                        :8192
                    ]
                if fail.stderr:
                    extra["stderr"] = fail.stderr.decode("utf-8", errors="replace")[
                        :8192
                    ]
            self._send_error(result.http_status, "command failed", extra=extra)
            return

        omit_body = self.command == "HEAD"
        if self.command == "HEAD" and isinstance(parsed, PipelineParse):
            if not all(head_permitted(s.metadata) for s in parsed.stages):
                self._send_error(405, "method HEAD not permitted")
                return
        elif self.command == "HEAD" and isinstance(parsed, RawCommandParse):
            if not head_permitted(parsed.stage.metadata):
                self._send_error(405, "method HEAD not permitted")
                return

        content_type = infer_mime_from_bytes(result.stdout, result.content_type)
        self._send_response(
            200,
            result.stdout,
            content_type=content_type,
            extra_headers=self._pipeline_headers(result),
            omit_body=omit_body,
        )

    def _dispatch(self) -> None:
        raw_target = self._raw_target()
        method = self.command
        config = self.server.config

        if method in ("PUT", "DELETE"):
            self._handle_put_delete_literal(method, raw_target)
            return

        body = self._request_body() if method in ("POST", "PUT", "PATCH") else b""

        try:
            parsed = parse_request(
                method,
                raw_target,
                config.root,
                command_dirs=config.command_dirs,
            )
        except ParseError as exc:
            self._send_error(exc.status, exc.message)
            return

        if isinstance(parsed, FilesystemParse):
            if method == "GET" or method == "HEAD":
                self._handle_filesystem_get(parsed)
                return
            if method == "POST":
                self._send_error(405, "POST not permitted for plain file resource")
                return
            self._send_error(405, f"method {method} not permitted")
            return

        if isinstance(parsed, NotFoundParse):
            self._send_error(404, "not found")
            return

        if method == "POST" and isinstance(parsed, PipelineParse):
            for stage in parsed.stages:
                if "POST" not in stage.metadata.methods:
                    self._send_error(
                        405, f"method POST not permitted by command {stage.name}"
                    )
                    return

        self._handle_command(parsed, body=body)

    def do_GET(self) -> None:
        self._dispatch()

    def do_HEAD(self) -> None:
        self._dispatch()

    def do_PUT(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


def create_server(root: Path, host: str, port: int) -> tuple[WashHTTPServer, int]:
    config = ServerConfig(root)
    if port == 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, 0))
        actual_port = sock.getsockname()[1]
        sock.close()
        httpd = WashHTTPServer((host, actual_port), WashRequestHandler, config)
        return httpd, actual_port
    httpd = WashHTTPServer((host, port), WashRequestHandler, config)
    return httpd, port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="wash reference runtime server")
    parser.add_argument("--root", required=True, help="project root directory")
    parser.add_argument("--port", type=int, default=0, help="TCP port (0 = ephemeral)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 1

    httpd, bound_port = create_server(root, BIND_HOST, args.port)

    if args.port == 0:
        print(f"WASH-PORT {bound_port}", flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
