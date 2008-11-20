import BaseHTTPServer
import threading
import unittest
import time
import os

from smart.progress import Progress
from smart.fetcher import Fetcher
from smart.const import VERSION

from tests.mocker import MockerTestCase


PORT = 43543
URL = "http://127.0.0.1:%d/filename.pkg" % PORT


class FetcherTest(MockerTestCase):

    def setUp(self):
        self.local_path = self.makeDir()
        self.fetcher = Fetcher()
        self.fetcher.setLocalPathPrefix(self.local_path + "/")

    def start_server(self, handler):
        def server():
            class Handler(BaseHTTPServer.BaseHTTPRequestHandler):
                def do_GET(self):
                    return handler(self)
            httpd = BaseHTTPServer.HTTPServer(("127.0.0.1", PORT), Handler)
            httpd.handle_request()
        self.server_thread = threading.Thread(target=server)
        self.server_thread.start()
        time.sleep(0.5)

    def wait_for_server(self):
        self.server_thread.join()

    def test_user_agent(self):
        headers = []
        def handler(request):
            headers[:] = request.headers.headers
        self.start_server(handler)
        self.fetcher.enqueue(URL)
        self.fetcher.run(progress=Progress())
        self.assertTrue(("User-Agent: smart/%s\r\n" % VERSION) in headers)

    def test_remove_pragma_no_cache_from_curl(self):
        headers = []
        def handler(request):
            headers[:] = request.headers.headers
        self.start_server(handler)
        old_http_proxy = os.environ.get("http_proxy")
        os.environ["http_proxy"] = URL
        try:
            self.fetcher.enqueue(URL)
            self.fetcher.run(progress=Progress())
        finally:
            if old_http_proxy:
                os.environ["http_proxy"] = old_http_proxy
            else:
                del os.environ["http_proxy"]
        self.assertTrue("Pragma: no-cache\r\n" not in headers)

    def test_404_handling(self):
        headers = []
        def handler(request):
            request.send_error(404, "An expected error")
            request.send_header("Content-Length", "6")
            request.wfile.write("Hello!")
        self.start_server(handler)
        self.fetcher.enqueue(URL)
        self.fetcher.run(progress=Progress())
        item = self.fetcher.getItem(URL)
        self.assertEquals(item.getFailedReason(), u"File not found")