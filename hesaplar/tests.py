from django.test import RequestFactory, SimpleTestCase, override_settings

from hesaplar.yetki import istemci_ip


class IstemciIpTest(SimpleTestCase):
    """Giriş kilidi (django-axes) için kullanılan IP: proxy başlığına yalnızca canlıda güvenilir."""

    def _istek(self):
        return RequestFactory().get('/', REMOTE_ADDR='10.0.0.1', HTTP_X_REAL_IP='203.0.113.7')

    @override_settings(PROXY_ARKASINDA=True)
    def test_proxy_arkasinda_x_real_ip_kullanilir(self):
        self.assertEqual(istemci_ip(self._istek()), '203.0.113.7')

    @override_settings(PROXY_ARKASINDA=False)
    def test_yerelde_baslik_taklit_edilemez(self):
        self.assertEqual(istemci_ip(self._istek()), '10.0.0.1')
