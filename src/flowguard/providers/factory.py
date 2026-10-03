from flowguard.config import Settings
from flowguard.providers.base import SapProvider
from flowguard.providers.hybrid import HybridSapProvider
from flowguard.providers.mock import MockSapProvider
from flowguard.providers.sandbox import SapSandboxProvider


def create_provider(settings: Settings) -> SapProvider:
    mock = MockSapProvider(settings.sap_mock_base_url, settings.request_timeout_seconds)
    if settings.sap_mode == "mock":
        return mock

    if settings.sap_mode in {"sandbox", "hybrid"}:
        if not settings.sap_api_key:
            raise ValueError(f"SAP_API_KEY is required when SAP_MODE={settings.sap_mode}")
        sandbox = SapSandboxProvider(
            settings.sap_sandbox_base_url,
            settings.sap_api_key.get_secret_value(),
            settings.request_timeout_seconds,
        )
        return HybridSapProvider(sandbox, mock) if settings.sap_mode == "hybrid" else sandbox

    if settings.sap_mode == "live":
        raise NotImplementedError(
            "SAP live mode requires tenant-specific communication arrangements; "
            "use mock, sandbox or hybrid until configured."
        )
    raise ValueError(f"Unsupported SAP_MODE: {settings.sap_mode}")
