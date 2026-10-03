from copy import deepcopy
from datetime import date, timedelta

BASE_DATA = {
    "sales_orders": [
        {
            "SalesOrder": "5000000010",
            "CompanyCode": "1000",
            "SalesOrganization": "1010",
            "SoldToParty": "1000001",
            "TotalNetAmount": "25000.00",
            "TransactionCurrency": "BRL",
            "SalesOrderDate": "2026-09-25",
            "OverallSDProcessStatus": "C",
        },
        {
            "SalesOrder": "5000000011",
            "CompanyCode": "1000",
            "SalesOrganization": "1010",
            "SoldToParty": "1000002",
            "TotalNetAmount": "125000.00",
            "TransactionCurrency": "BRL",
            "SalesOrderDate": "2026-09-27",
            "OverallSDProcessStatus": "C",
        },
    ],
    "billings": [
        {
            "BillingDocument": "9000000010",
            "CompanyCode": "1000",
            "SalesDocument": "5000000010",
            "AccountingDocument": "1900000010",
            "TotalNetAmount": "25000.00",
            "TransactionCurrency": "BRL",
            "BillingDocumentDate": "2026-09-26",
            "BillingDocumentIsCancelled": False,
        },
        {
            "BillingDocument": "9000000011",
            "CompanyCode": "1000",
            "SalesDocument": "5000000011",
            "AccountingDocument": "1900000011",
            "TotalNetAmount": "125000.00",
            "TransactionCurrency": "BRL",
            "BillingDocumentDate": "2026-09-28",
            "BillingDocumentIsCancelled": False,
        },
    ],
    "purchase_orders": [
        {
            "PurchaseOrder": "4500000010",
            "CompanyCode": "1000",
            "Supplier": "2000001",
            "PurchaseOrderNetAmount": "100000.00",
            "GoodsReceiptAmount": "100000.00",
            "DocumentCurrency": "BRL",
            "PurchaseOrderDate": "2026-09-20",
            "PurchasingProcessingStatus": "C",
        }
    ],
    "supplier_invoices": [
        {
            "SupplierInvoice": "5100000010",
            "CompanyCode": "1000",
            "PurchaseOrder": "4500000010",
            "InvoicingParty": "2000001",
            "InvoiceGrossAmount": "100000.00",
            "DocumentCurrency": "BRL",
            "DocumentDate": "2026-09-23",
            "PaymentBlockingReason": "",
            "SupplierInvoiceStatus": "POSTED",
        }
    ],
    "journal_entries": [
        {
            "AccountingDocument": "1900000010",
            "CompanyCode": "1000",
            "ReferenceDocument": "9000000010",
            "AmountInCompanyCodeCurrency": "25000.00",
            "CompanyCodeCurrency": "BRL",
            "DocumentDate": "2026-09-26",
            "PostingDate": "2026-09-26",
        },
        {
            "AccountingDocument": "1900000011",
            "CompanyCode": "1000",
            "ReferenceDocument": "9000000011",
            "AmountInCompanyCodeCurrency": "125000.00",
            "CompanyCodeCurrency": "BRL",
            "DocumentDate": "2026-09-28",
            "PostingDate": "2026-09-28",
        },
    ],
}


SCENARIOS = {
    "normal",
    "blocked_invoice",
    "duplicate_invoice",
    "billing_without_fi",
    "po_price_variance",
    "quantity_variance",
    "late_billing",
    "duplicate_journal",
    "cross_module_reference_break",
    "api_timeout",
    "odata_pagination",
    "csrf_failure",
    "etag_conflict",
}


def load_scenario(name: str) -> dict:
    if name not in SCENARIOS:
        raise ValueError(f"Unknown scenario {name}")
    data = deepcopy(BASE_DATA)
    if name == "billing_without_fi":
        data["billings"][1]["AccountingDocument"] = ""
    elif name == "blocked_invoice":
        data["supplier_invoices"][0]["PaymentBlockingReason"] = "A"
        data["supplier_invoices"][0]["DocumentDate"] = str(date.today() - timedelta(days=7))
    elif name == "po_price_variance":
        data["supplier_invoices"][0]["InvoiceGrossAmount"] = "107500.00"
        data["supplier_invoices"][0]["PaymentBlockingReason"] = "A"
        data["supplier_invoices"][0]["DocumentDate"] = str(date.today() - timedelta(days=7))
    elif name == "duplicate_invoice":
        duplicate = deepcopy(data["supplier_invoices"][0])
        duplicate["SupplierInvoice"] = "5100000011"
        data["supplier_invoices"].append(duplicate)
    elif name == "quantity_variance":
        data["supplier_invoices"][0]["InvoicedQuantity"] = "120"
        data["purchase_orders"][0]["ReceivedQuantity"] = "100"
    elif name == "late_billing":
        data["billings"] = data["billings"][:1]
    elif name == "duplicate_journal":
        duplicate = deepcopy(data["journal_entries"][0])
        duplicate["AccountingDocument"] = "1900000012"
        data["journal_entries"].append(duplicate)
    elif name == "cross_module_reference_break":
        data["billings"][0]["SalesDocument"] = "5999999999"
    return data
