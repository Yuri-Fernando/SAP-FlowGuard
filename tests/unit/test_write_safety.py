import asyncio
from uuid import uuid4

import pytest

from flowguard.config import Settings
from flowguard.persistence import Repository
from flowguard.providers.base import SapProvider, SapWriteError
from flowguard.services import WritebackService


class NeverCalledProvider(SapProvider):
    name = "never-called"

    async def health_check(self):
        return True

    async def discover_capabilities(self):
        raise AssertionError

    async def list_sales_orders(self):
        return []

    async def list_billing_documents(self):
        return []

    async def list_purchase_orders(self):
        return []

    async def list_supplier_invoices(self):
        return []

    async def list_journal_entries(self):
        return []

    async def write(self, action, payload, etag=None):
        raise AssertionError("Provider must not be called while writes are disabled")


def test_writeback_is_disabled_by_default(tmp_path):
    repository = Repository(f"sqlite:///{tmp_path / 'test.db'}")
    repository.create_schema()
    service = WritebackService(NeverCalledProvider(), repository, Settings())

    with pytest.raises(SapWriteError, match="ENABLE_SAP_WRITE=false"):
        asyncio.run(
            service.execute(
                action="release_supplier_invoice",
                payload={"invoice": "INV1"},
                idempotency_key="release-INV1-v1",
                actor="tester",
                correlation_id=uuid4(),
                approval_id=None,
                etag=None,
            )
        )
