"""_harvest (Мегастрой) — ready_check не должен ложно считать капчу пройденной
из-за регистра title (баг: страница отдаёт "DDOS-GUARD", проверка сравнивала
только с "DDoS-Guard" — сравнение было всегда true, харвест кэшировал cookie
капча-страницы как успешный)."""
from app.parsers import headless_session


class _FakePage:
    def __init__(self, title: str):
        self._title = title

    def title(self) -> str:
        return self._title


def _captured_ready_check(monkeypatch):
    captured = {}

    def fake_collect_cookies(url, user_agent, *, site_label, ready_check=None):
        captured["ready_check"] = ready_check
        return None  # харвест "не удался" — нам нужен только сам callback

    monkeypatch.setattr(headless_session, "_collect_cookies", fake_collect_cookies)
    headless_session._harvest("https://kazan.megastroy.com/catalog/x", "UA")
    return captured["ready_check"]


def test_ready_check_rejects_ddos_guard_title_any_case(monkeypatch):
    ready_check = _captured_ready_check(monkeypatch)

    assert ready_check(_FakePage("DDoS-Guard")) is False
    assert ready_check(_FakePage("DDOS-GUARD")) is False
    assert ready_check(_FakePage("ddos-guard")) is False


def test_ready_check_accepts_real_catalog_title(monkeypatch):
    ready_check = _captured_ready_check(monkeypatch)

    assert ready_check(_FakePage("Ламинат — купить в Казани | Мегастрой")) is True
