import hashlib
import hmac
import json
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shrucloud import VERSION, Client, ShruError, sign  # noqa: E402

SECRET = "test-secret-0123456789"
KEY = "hmac_0123456789abcdef"


def standard_api(request):
    action = request.get("action")
    if action == "account_info":
        return 200, {"success": True, "balance": 12.5, "currency": "USD", "email": "a@b.c"}
    if action == "sync":
        return 200, {"success": True, "balance": 12.5, "currency": "USD", "services": [{"id": 7, "name": "Check"}]}
    if action == "submit_order":
        return 200, {"success": True, "order_id": 99, "status": "queued"}
    if action == "check_status":
        return 200, {"success": True, "order_id": request["order_id"], "status": "completed", "reply": "Done"}
    return 400, {"success": False, "message": "Unknown action"}


class ShruServer:
    """A small SHRU endpoint for the tests: answers only at `path`, checks
    every signature the way a platform does, and records what it received."""

    def __init__(self, path, handler=standard_api, raw=None):
        self.seen = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8")
                outer.seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
                if raw is not None:
                    raw(self)
                    return
                if self.path != path:
                    self._send(404, b"<h1>Not found</h1>", "text/html")
                    return
                expected = hmac.new(
                    SECRET.encode(),
                    ("POST\n/api/shru\n" + self.headers["X-Timestamp"] + "\n" + body).encode(),
                    hashlib.sha256,
                ).hexdigest()
                if self.headers["X-Key-Id"] != KEY or self.headers["X-Signature"] != expected:
                    status, data = 401, {"success": False, "message": "Invalid signature"}
                else:
                    status, data = handler(json.loads(body))
                self._send(status, json.dumps(data).encode(), "application/json")

            def _send(self, status, payload, content_type):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def local(base, **extra):
    return Client(base, KEY, SECRET, allow_insecure_http=True, **extra)


class ClientTest(unittest.TestCase):
    def serve(self, *args, **kwargs):
        server = ShruServer(*args, **kwargs)
        self.addCleanup(server.close)
        return server

    def test_signs_exactly_like_the_api_documentation_test_vector(self):
        secret = (
            "9f2d6c1e8b4a7d3f5e0c2b9a6d8f1e4c7b3a5d9e2f6c8b1a4d7e0f3c6b9a2d5e8f1c4b7a0d3e6f9c2b5a8d1e4f7c0b3a6d9e2f5c8b"
            "1a4d7e0f3c6b9a2d5e8f1c"
        )
        body = '{"action":"submit_order","service_id":1042,"input":"356789101234567"}'
        self.assertEqual(sign(secret, "1767225600", body), "e2bf80ed81ffaa94829122e0655d795c446609fadfb952c9025866d54f6b8fa5")

    def test_refuses_plain_http_bad_input_and_a_short_timeout(self):
        with self.assertRaisesRegex(ValueError, "plain HTTP"):
            Client("http://reseller.example.com", KEY, SECRET)
        with self.assertRaisesRegex(ValueError, "Unsupported URL scheme"):
            Client("ftp://reseller.example.com", KEY, SECRET)
        with self.assertRaisesRegex(ValueError, "required"):
            Client("", KEY, SECRET)
        with self.assertRaisesRegex(ValueError, "at least 1"):
            Client("https://reseller.example.com", KEY, SECRET, timeout_seconds=0)
        Client("reseller.example.com", KEY, SECRET)

    def test_the_full_api_address_is_used_as_given(self):
        client = Client("https://reseller.example.com/api/shru/", KEY, SECRET)
        self.assertEqual(client.endpoint(), "https://reseller.example.com/api/shru")

    def test_finds_the_endpoint_from_the_domain_and_calls_every_action(self):
        api = self.serve("/api/shru")
        client = local(api.base)
        self.assertEqual(client.account_info(), {"success": True, "balance": 12.5, "currency": "USD", "email": "a@b.c"})
        self.assertEqual(client.endpoint(), api.base + "/api/shru")
        self.assertEqual(client.sync_catalog(), {"balance": 12.5, "currency": "USD", "services": [{"id": 7, "name": "Check"}]})
        self.assertEqual(client.sync_services(), [{"id": 7, "name": "Check"}])
        self.assertEqual(client.place_order(7, "356789101234567", 1, {"Username": "bob"})["order_id"], 99)
        self.assertEqual(client.check_status(99)["reply"], "Done")
        order = next(r for r in api.seen if "submit_order" in r["body"])
        self.assertEqual(
            json.loads(order["body"]),
            {"action": "submit_order", "service_id": 7, "input": "356789101234567", "quantity": 1, "fields": {"Username": "bob"}},
        )
        self.assertTrue(order["headers"]["User-Agent"].startswith("SHRU_Cloud-Python-SDK/%s " % VERSION))
        self.assertEqual(order["headers"]["Accept"], "application/json")

    def test_finds_a_platform_installed_in_a_subfolder(self):
        api = self.serve("/shop/api/shru")
        client = local(api.base + "/shop")
        client.account_info()
        self.assertEqual(client.endpoint(), api.base + "/shop/api/shru")

    def test_a_shru_format_refusal_proves_the_address(self):
        api = self.serve("/api/shru", lambda request: (403, {"success": False, "message": "Unauthorized access"}))
        client = local(api.base)
        with self.assertRaises(ShruError) as caught:
            client.account_info()
        self.assertEqual(caught.exception.status, 403)
        self.assertTrue(caught.exception.is_auth_error())
        self.assertEqual(str(caught.exception), "Unauthorized access")
        self.assertIs(caught.exception.response["success"], False)
        self.assertEqual(client.endpoint(), api.base + "/api/shru")

    def test_an_api_rejection_keeps_the_server_message(self):
        def handler(request):
            if request["action"] == "account_info":
                return 200, {"success": True, "balance": 0, "currency": "USD", "email": ""}
            return 400, {"success": False, "message": "Insufficient balance"}

        api = self.serve("/api/shru", handler)
        with self.assertRaises(ShruError) as caught:
            local(api.base).place_order(7, "x")
        self.assertEqual(str(caught.exception), "Insufficient balance")
        self.assertEqual(caught.exception.status, 400)
        self.assertFalse(caught.exception.is_auth_error())

    def test_a_reply_that_is_not_json_is_reported_with_its_status(self):
        def bad_gateway(handler):
            handler._send(502, b"<html>Bad gateway</html>", "text/html")

        api = self.serve("/api/shru", raw=bad_gateway)
        with self.assertRaises(ShruError) as caught:
            local(api.base + "/api/shru").account_info()
        self.assertEqual(caught.exception.status, 502)
        self.assertIn("non-JSON", str(caught.exception))

    def test_never_follows_a_redirect(self):
        elsewhere = self.serve("/api/shru")

        def redirect(handler):
            handler.send_response(301)
            handler.send_header("Location", elsewhere.base + "/api/shru")
            handler.send_header("Content-Length", "0")
            handler.end_headers()

        api = self.serve("/api/shru", raw=redirect)
        with self.assertRaises(ShruError) as caught:
            local(api.base + "/api/shru").account_info()
        self.assertEqual(caught.exception.status, 301)
        self.assertEqual(elsewhere.seen, [])

    def test_gives_up_after_the_timeout(self):
        api = self.serve("/api/shru", raw=lambda handler: time.sleep(3))
        started = time.monotonic()
        with self.assertRaises(ShruError) as caught:
            local(api.base + "/api/shru", timeout_seconds=1).account_info()
        self.assertEqual(caught.exception.status, 0)
        self.assertLess(time.monotonic() - started, 2.5)

    def test_a_server_that_cannot_be_reached_is_status_0(self):
        api = ShruServer("/api/shru")
        base = api.base
        api.close()
        with self.assertRaises(ShruError) as caught:
            local(base + "/api/shru").account_info()
        self.assertEqual(caught.exception.status, 0)
        self.assertIn("Connection to SHRU Cloud failed", str(caught.exception))

    def test_calls_from_several_threads_look_for_the_endpoint_once(self):
        api = self.serve("/api/shru")
        client = local(api.base)
        threads = [threading.Thread(target=client.account_info) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(api.seen), 6)

    def test_rejects_wrong_argument_types_before_sending(self):
        client = Client("https://reseller.example.com/api/shru", KEY, SECRET)
        for args in (("7", "x"), (7, 123), (7, "x", 1.5), (7, "x", True), (7, "x", 1, ["a"])):
            with self.assertRaises(TypeError):
                client.place_order(*args)
        with self.assertRaises(TypeError):
            client.check_status(0)


if __name__ == "__main__":
    unittest.main()
