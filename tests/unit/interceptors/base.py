import asyncio
from collections.abc import Sequence
import json
from typing import Mapping, Optional, Tuple

import pytest

import pook


class StandardTests:
    is_async: bool = False
    loop: asyncio.AbstractEventLoop

    async def amake_request(
        self,
        method: str,
        url: str,
        content: Optional[bytes] = None,
        headers: Optional[Sequence[tuple[str, str]]] = None,
    ) -> Tuple[int, Optional[bytes], Mapping[str, str]]:
        raise NotImplementedError(
            "Sub-classes for async transports must implement `amake_request`"
        )

    def make_request(
        self,
        method: str,
        url: str,
        content: Optional[bytes] = None,
        headers: Optional[Sequence[tuple[str, str]]] = None,
    ) -> Tuple[int, Optional[bytes], Mapping[str, str]]:
        if self.is_async:
            return self.loop.run_until_complete(
                self.amake_request(method, url, content, headers)
            )

        raise NotImplementedError("Sub-classes must implement `make_request`")

    @pytest.fixture(autouse=True, scope="class")
    def _loop(self, request):
        if self.is_async:
            request.cls.loop = asyncio.new_event_loop()
            yield
            request.cls.loop.close()
        else:
            yield

    @pytest.fixture
    def url_404(self, httpbin):
        """404 httpbin URL.

        Useful in tests if pook is configured to reply 200, and the status is checked.
        If pook does not match the request (and if that was the intended behaviour)
        then the 404 status code makes that obvious!"""
        return f"{httpbin.url}/status/404"

    @pytest.fixture
    def url_500(self, httpbin):
        return f"{httpbin.url}/status/500"

    @pytest.mark.pook
    def test_activate_deactivate(self, url_404):
        """Deactivating pook allows requests to go through."""
        pook.get(url_404).reply(200).body("hello from pook")

        status, body, *_ = self.make_request("GET", url_404)

        assert status == 200
        assert body == b"hello from pook"

        pook.disable()

        status, body, *_ = self.make_request("GET", url_404)

        assert status == 404

    @pytest.mark.pook(allow_pending_mocks=True)
    def test_network_mode(self, url_404, url_500):
        """Enabling network mode allows requests to pass through even if no mock is matched."""
        pook.get(url_404).reply(200).body("hello from pook")
        pook.enable_network()

        # Avoid matching the mocks
        status, *_ = self.make_request("POST", url_500)

        assert status == 500

    @pytest.mark.pook
    def test_json_request(self, url_404):
        """JSON request bodies are correctly matched."""
        json_request = {"hello": "json-request"}
        pook.get(url_404).json(json_request).reply(200).body("hello from pook")

        status, body, *_ = self.make_request(
            "GET", url_404, json.dumps(json_request).encode()
        )

        assert status == 200
        assert body == b"hello from pook"

    @pytest.mark.pook
    def test_json_response(self, url_404):
        """JSON responses are correctly mocked."""
        json_response = {"hello": "json-request"}
        pook.get(url_404).reply(200).json(json_response)

        status, body, *_ = self.make_request("GET", url_404)

        assert status == 200
        assert body
        assert json.loads(body) == json_response

    @pytest.mark.pook
    def test_json_request_and_response(self, url_404):
        """JSON requests and responses do not interfere with each other."""
        json_request = {"id": "123abc"}
        json_response = {"title": "123abc title"}
        pook.get(url_404).json(json_request).reply(200).json(json_response)

        status, body, *_ = self.make_request(
            "GET", url_404, content=json.dumps(json_request).encode()
        )

        assert status == 200
        assert body
        assert json.loads(body) == json_response

    @pytest.mark.pook
    def test_header_sent(self, url_404):
        """Sent headers can be matched."""
        headers = [("x-hello", "from pook")]
        pook.get(url_404).header("x-hello", "from pook").reply(200).body(
            "hello from pook"
        )

        status, body, _ = self.make_request("GET", url_404, headers=headers)

        assert status == 200
        assert body == b"hello from pook"

    @pytest.mark.pook
    def test_mocked_resposne_headers(self, url_404):
        """Mocked response headers are appropriately returned."""
        pook.get(url_404).reply(200).header("x-hello", "from pook")

        status, _, headers = self.make_request("GET", url_404)

        assert status == 200
        assert headers["x-hello"] == "from pook"

    @pytest.mark.pook
    def test_mutli_value_headers(self, url_404):
        """Multi-value headers can be matched."""
        match_headers = [("x-hello", "from pook"), ("x-hello", "another time")]
        pook.get(url_404).header("x-hello", "from pook, another time").reply(200)

        status, *_ = self.make_request("GET", url_404, headers=match_headers)

        assert status == 200

    @pytest.mark.pook
    def test_mutli_value_response_headers(self, url_404):
        """Multi-value response headers can be mocked."""
        pook.get(url_404).reply(200).header("x-hello", "from pook").header(
            "x-hello", "another time"
        )

        status, _, headers = self.make_request("GET", url_404)

        assert status == 200
        assert headers["x-hello"] == "from pook, another time"
