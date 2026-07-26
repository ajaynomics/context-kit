#!/usr/bin/env python3
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path


EXPECTED_VERSIONS = {
    "mcp-proxy": "0.12.0",
    "mcp": "1.28.1",
}


def module_path(name: str) -> Path:
    spec = find_spec(name)
    if spec is None or spec.origin is None:
        raise RuntimeError(f"module not found: {name}")
    return Path(spec.origin)


def replace_once(path: Path, before: str, after: str) -> None:
    source = path.read_text()
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"expected one patch target in {path}, found {count}: {before}")
    path.write_text(source.replace(before, after))


for package, expected in EXPECTED_VERSIONS.items():
    actual = version(package)
    if actual != expected:
        raise RuntimeError(f"expected {package} {expected}, found {actual}")


proxy_path = module_path("mcp_proxy.proxy_server")
replace_once(
    proxy_path,
    "import logging\nimport typing as t\n\nfrom mcp import server, types",
    "import logging\nimport typing as t\n\nimport anyio\n\nfrom mcp import server, types",
)
replace_once(
    proxy_path,
    """                result = await remote_app.call_tool(
                    req.params.name,
                    (req.params.arguments or {}),
                    meta=meta_dict,
                    progress_callback=progress_callback,
                )
""",
    """                completed = anyio.Event()
                disconnected = False
                downstream_request = request_ctx.get().request

                async def watch_downstream_disconnect() -> None:
                    nonlocal disconnected
                    while not completed.is_set():
                        if await downstream_request.is_disconnected():
                            disconnected = True
                            task_group.cancel_scope.cancel()
                            return
                        await anyio.sleep(0.05)

                async with anyio.create_task_group() as task_group:
                    if downstream_request is not None and hasattr(downstream_request, "is_disconnected"):
                        task_group.start_soon(watch_downstream_disconnect)
                    try:
                        result = await remote_app.call_tool(
                            req.params.name,
                            (req.params.arguments or {}),
                            meta=meta_dict,
                            progress_callback=progress_callback,
                        )
                    finally:
                        completed.set()
                        task_group.cancel_scope.cancel()

                if disconnected:
                    raise ConnectionError("downstream client disconnected")
""",
)


session_path = module_path("mcp.shared.session")
replace_once(
    session_path,
    """        finally:
            self._response_streams.pop(request_id, None)
            self._progress_callbacks.pop(request_id, None)
""",
    """        except anyio.get_cancelled_exc_class():
            # Context Kit: forward cancellation before abandoning the remote request.
            with anyio.move_on_after(1, shield=True):
                try:
                    await self.send_notification(
                        CancelledNotification(
                            params={"requestId": request_id, "reason": "upstream request cancelled"}
                        )
                    )
                except Exception:
                    pass
            raise
        finally:
            self._response_streams.pop(request_id, None)
            self._progress_callbacks.pop(request_id, None)
""",
)


streamable_http_path = module_path("mcp.client.streamable_http")
replace_once(
    streamable_http_path,
    """        self.url = url
        self.session_id = None
        self.protocol_version = None
""",
    """        self.url = url
        self.session_id = None
        self.protocol_version = None
        self._request_cancel_scopes: dict[RequestId, anyio.CancelScope] = {}
""",
)
replace_once(
    streamable_http_path,
    """                    async def handle_request_async():
                        if is_resumption:
                            await self._handle_resumption_request(ctx)
                        else:
                            await self._handle_post_request(ctx)

                    # If this is a request, start a new task to handle it
                    if isinstance(message.root, JSONRPCRequest):
                        tg.start_soon(handle_request_async)
                    else:
                        await handle_request_async()
""",
    """                    async def handle_request_async(
                        request_context: RequestContext = ctx,
                        resume: bool = is_resumption,
                    ) -> None:
                        root = request_context.session_message.message.root
                        request_id = root.id if isinstance(root, JSONRPCRequest) else None
                        with anyio.CancelScope() as request_scope:
                            if request_id is not None:
                                self._request_cancel_scopes[request_id] = request_scope
                            try:
                                if resume:
                                    await self._handle_resumption_request(request_context)
                                else:
                                    await self._handle_post_request(request_context)
                            finally:
                                if self._request_cancel_scopes.get(request_id) is request_scope:
                                    self._request_cancel_scopes.pop(request_id, None)

                    # If this is a request, start a new task to handle it
                    if isinstance(message.root, JSONRPCRequest):
                        tg.start_soon(handle_request_async)
                    else:
                        if (
                            isinstance(message.root, JSONRPCNotification)
                            and message.root.method == "notifications/cancelled"
                        ):
                            request_scope = self._request_cancel_scopes.get(
                                (message.root.params or {}).get("requestId")
                            )
                            if request_scope is not None:
                                request_scope.cancel()
                        await handle_request_async()
""",
)
