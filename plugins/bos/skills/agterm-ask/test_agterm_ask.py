import importlib.machinery
import os
import threading
import urllib.request

mod = importlib.machinery.SourceFileLoader(
    "agterm_ask", os.path.join(os.path.dirname(__file__), "agterm-ask")).load_module()


def test_page_wraps_body_and_post_lands_answer():
    page = mod.PAGE.format(title="T", body='<input name="choice" value="a">')
    assert '<form method="post" action="/answer">' in page and 'value="a"' in page
    server = mod.make_server(page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    assert b'value="a"' in urllib.request.urlopen(url).read()
    urllib.request.urlopen(url + "answer", data=b"choice=a&choice=c&note=%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82")
    assert server.answer == {"choice": ["a", "c"], "note": "привет"}
    urllib.request.urlopen(url + "answer", data=b"choice=b")  # first answer wins
    assert server.answer["choice"] == ["a", "c"]
    assert b"Answer sent" in urllib.request.urlopen(url).read()
    urllib.request.urlopen(url + "draft", data=b"choice=b&note=")
    assert server.draft == {"choice": ["b"], "note": ""}
    server.shutdown()
