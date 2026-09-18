from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from torremolinos import onedrive


class OneDriveClientTests(unittest.TestCase):
    def test_microsoft_requests_disable_compressed_responses(self):
        session = Mock()
        session.headers = {}
        application = object()

        with (
            patch.object(onedrive.requests, "Session", return_value=session),
            patch.object(
                onedrive.msal,
                "PublicClientApplication",
                return_value=application,
            ) as public_client,
        ):
            result = onedrive._application(cache="cache")

        self.assertIs(result, application)
        self.assertEqual(session.headers["Accept-Encoding"], "identity")
        public_client.assert_called_once_with(
            onedrive.CLIENT_ID,
            authority=onedrive.AUTHORITY,
            token_cache="cache",
            http_client=session,
        )


if __name__ == "__main__":
    unittest.main()
