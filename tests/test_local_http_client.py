import unittest

from fastapi import FastAPI, Request, Response

from tests.local_client import LocalASGIClient


class LocalASGIClientTests(unittest.TestCase):
    def test_requests_and_cookies_work_without_a_threaded_testclient_portal(self) -> None:
        app = FastAPI()

        @app.get("/set-cookie")
        def set_cookie(response: Response) -> dict[str, bool]:
            response.set_cookie("session", "local-test")
            return {"ok": True}

        @app.get("/echo-cookie")
        def echo_cookie(request: Request) -> dict[str, str | None]:
            return {"session": request.cookies.get("session")}

        client = LocalASGIClient(app, base_url="https://testserver")

        self.assertEqual(200, client.get("/set-cookie").status_code)
        self.assertEqual(
            {"session": "local-test"},
            client.get("/echo-cookie").json(),
        )

        client.cookies.clear()
        self.assertEqual({"session": None}, client.get("/echo-cookie").json())


if __name__ == "__main__":
    unittest.main()
