"""Populate the Jupyter skill scaffold with the reproducible FlowGuard tutorial."""

import json
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).parents[1]
NOTEBOOK = ROOT / "output" / "jupyter-notebook" / "sap-flowguard-end-to-end.ipynb"


def source(text: str) -> list[str]:
    return dedent(text).lstrip("\n").splitlines(keepends=True)


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source(text)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source(text),
    }


def main() -> None:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    notebook["cells"] = [
        markdown(
            """
            # SAP FlowGuard End-to-End

            **O2C, P2P, aprovação humana e writeback seguro no Mock SAP**

            Este tutorial demonstra o caminho completo de uma exceção sem depender de um tenant
            SAP pago e sem delegar decisões financeiras a um LLM.
            """
        ),
        markdown(
            """
            ## Público, pré-requisitos e objetivos

            **Público:** pessoas estudando integração SAP, automação n8n ou controles FI/SD/MM.

            **Pré-requisitos:** Docker Desktop e a stack iniciada com `docker compose up --build`.
            O notebook usa apenas a biblioteca padrão do Python para as chamadas HTTP.

            Ao final você saberá:

            - ativar cenários reproduzíveis no Mock SAP;
            - executar controles O2C e P2P pela API FlowGuard;
            - interpretar as regras determinísticas `SD002` e `MM005`;
            - criar e decidir uma aprovação;
            - comprovar que writeback permanece bloqueado por padrão;
            - verificar se o n8n está disponível, sem executar workflows automaticamente.
            """
        ),
        markdown(
            """
            ## Roteiro

            1. Configurar cliente HTTP e verificar a stack.
            2. Executar o cenário O2C `billing_without_fi`.
            3. Executar o cenário P2P `po_price_variance`.
            4. Criar e aprovar uma proposta de ação.
            5. Validar o bloqueio seguro de writeback.
            6. Consultar a saúde do n8n e experimentar outro cenário.
            """
        ),
        code(
            """
            import json
            from pprint import pprint
            from urllib.error import HTTPError, URLError
            from urllib.request import Request, urlopen

            FLOWGUARD_URL = "http://localhost:8000"
            MOCK_SAP_URL = "http://localhost:8080"
            N8N_URL = "http://localhost:5678"

            def call(method, path, *, base=FLOWGUARD_URL, body=None, timeout=10):
                payload = None if body is None else json.dumps(body).encode("utf-8")
                request = Request(
                    f"{base}{path}",
                    data=payload,
                    method=method,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                try:
                    with urlopen(request, timeout=timeout) as response:
                        raw = response.read().decode("utf-8")
                        try:
                            result = json.loads(raw) if raw else {}
                        except json.JSONDecodeError:
                            result = {"body": raw}
                        return response.status, result
                except HTTPError as error:
                    raw = error.read().decode("utf-8")
                    try:
                        detail = json.loads(raw)
                    except json.JSONDecodeError:
                        detail = {"detail": raw}
                    return error.code, detail
                except URLError as error:
                    return 0, {"detail": str(error.reason)}
            """
        ),
        markdown(
            "## 1. Saúde da stack\n\nSe a stack estiver desligada, as próximas células serão "
            "ignoradas com uma mensagem clara."
        ),
        code(
            """
            api_status, api_health = call("GET", "/health")
            mock_status, mock_health = call("GET", "/health", base=MOCK_SAP_URL)
            STACK_READY = api_status == 200 and mock_status == 200

            print("FlowGuard API:", api_status, api_health)
            print("Mock SAP:", mock_status, mock_health)
            print("Stack pronta:", STACK_READY)
            """
        ),
        markdown(
            """
            ## 2. O2C — billing sem documento FI

            O Mock SAP remove o `AccountingDocument` de um billing. A API normaliza Sales Orders e
            Billing Documents, correlaciona os documentos e executa as regras SD/CROSS.
            """
        ),
        code(
            """
            o2c_result = {}
            if STACK_READY:
                call("POST", "/mock/scenario/billing_without_fi", base=MOCK_SAP_URL)
                status, o2c_result = call("POST", "/runs/o2c")
                print("HTTP", status, "| documentos:", o2c_result.get("documents_processed"))
                for item in o2c_result.get("exceptions", []):
                    print(
                        item["rule_id"],
                        item["exception_type"],
                        item["severity"],
                        item["source_document_id"],
                    )
            else:
                print("Inicie a stack para executar o cenário O2C.")
            """
        ),
        markdown(
            """
            **Interpretação esperada:** `SD002 / BILLING_WITHOUT_FI` identifica a quebra entre SD e
            FI. A severidade é calculada deterministicamente pelo valor em risco.
            """
        ),
        markdown(
            """
            ## 3. P2P — invoice acima da tolerância

            O cenário usa PO de 100.000 e Supplier Invoice de 107.500. Com tolerância de 2%, a regra
            `MM005` deve apontar uma variação de 7.500 e exigir aprovação.
            """
        ),
        code(
            """
            p2p_result = {}
            mm005 = None
            if STACK_READY:
                call("POST", "/mock/scenario/po_price_variance", base=MOCK_SAP_URL)
                status, p2p_result = call("POST", "/runs/p2p")
                mm005 = next(
                    (x for x in p2p_result.get("exceptions", []) if x["rule_id"] == "MM005"),
                    None,
                )
                pprint({
                    "http_status": status,
                    "correlation_id": p2p_result.get("correlation_id"),
                    "rule": mm005.get("rule_id") if mm005 else None,
                    "amount_at_risk": mm005.get("amount_at_risk") if mm005 else None,
                    "approval_required": mm005.get("approval_required") if mm005 else None,
                    "evidence": mm005.get("evidence") if mm005 else None,
                })
            else:
                print("Inicie a stack para executar o cenário P2P.")
            """
        ),
        markdown(
            "## 4. Human-in-the-loop\n\nA aprovação fica vinculada à ação exata "
            "`release_supplier_invoice`."
        ),
        code(
            """
            approval = None
            if STACK_READY and mm005:
                status, approval = call("POST", "/approvals", body={
                    "exception_id": mm005["exception_id"],
                    "action": "release_supplier_invoice",
                    "requested_by": "notebook-demo",
                })
                print("Solicitação:", status, approval.get("state"))
                status, approval = call(
                    "POST",
                    f"/approvals/{approval['approval_id']}/decision",
                    body={
                        "decision": "APPROVE",
                        "decided_by": "portfolio-reviewer",
                        "reason": "Aprovação demonstrativa; flags de escrita continuam desligadas.",
                    },
                )
                print("Decisão:", status, approval.get("state"))
            else:
                print("Aprovação não criada: stack ou exceção MM005 indisponível.")
            """
        ),
        markdown(
            """
            ## 5. Safe writeback

            Mesmo com aprovação humana, a configuração padrão deve recusar a escrita porque
            `ENABLE_SAP_WRITE=false`. Este é o resultado correto e comprova defesa em profundidade.
            """
        ),
        code(
            """
            if STACK_READY and approval:
                status, writeback = call("POST", "/writebacks", body={
                    "action": "release_supplier_invoice",
                    "payload": {"supplier_invoice": mm005["source_document_id"]},
                    "idempotency_key": f"notebook-release-{mm005['source_document_id']}-v1",
                    "actor": "notebook-demo",
                    "correlation_id": p2p_result["correlation_id"],
                    "approval_id": approval["approval_id"],
                    "etag": "*",
                })
                print("HTTP esperado: 403 | recebido:", status)
                pprint(writeback)
                assert status == 403, (
                    "A escrita estava habilitada; confirme se isso foi intencional."
                )
            else:
                print("Writeback não tentado: pré-condições da demonstração ausentes.")
            """
        ),
        markdown(
            """
            ## 6. Saúde do n8n

            Esta célula apenas consulta `/healthz`. Ela não importa, ativa ou executa workflows.
            O dashboard mostra o histórico real quando `N8N_API_KEY` está configurada.
            """
        ),
        code(
            """
            n8n_status, n8n_health = call("GET", "/healthz", base=N8N_URL)
            print("n8n:", "online" if n8n_status == 200 else "indisponível", n8n_health)
            """
        ),
        markdown(
            """
            ## Exercício

            Troque o cenário para `duplicate_invoice`, execute P2P e confirme que `MM007` aparece
            duas vezes — uma para cada documento com a mesma assinatura de fornecedor, data, moeda e
            valor. Ative `RUN_EXERCISE` quando quiser executar.
            """
        ),
        code(
            """
            RUN_EXERCISE = False
            if RUN_EXERCISE and STACK_READY:
                call("POST", "/mock/scenario/duplicate_invoice", base=MOCK_SAP_URL)
                _, exercise = call("POST", "/runs/p2p")
                duplicates = [x for x in exercise["exceptions"] if x["rule_id"] == "MM007"]
                assert len(duplicates) == 2
                pprint(duplicates)
            else:
                print("Defina RUN_EXERCISE=True para executar a resposta guiada.")
            """
        ),
        markdown(
            """
            ## Armadilhas e extensões

            - **Erro comum:** habilitar `ENABLE_SAP_WRITE` e esquecer a flag específica da ação.
              Ambos os controles são obrigatórios, além da aprovação quando configurada.
            - **Sandbox SAP:** trate como leitura/contract test; não presuma suporte a escrita.
            - **Extensão:** configure uma API key do n8n e acompanhe workflows e execuções no
              dashboard em `http://localhost:8501`.
            - **Extensão:** implemente SOAP FI e HANA mantendo o mesmo modelo canônico.
            """
        ),
        markdown("## 7. Restaurar cenário normal"),
        code(
            """
            if STACK_READY:
                status, reset = call("POST", "/mock/scenario/normal", base=MOCK_SAP_URL)
                print("Mock SAP restaurado:", status, reset.get("active"))
            """
        ),
        markdown(
            """
            ## Conclusão

            O fluxo demonstrou integração SAP-shaped, correlação cross-module, regras
            determinísticas, aprovação humana e bloqueio seguro de escrita. O n8n permanece como
            orquestrador, enquanto os controles financeiros e de segurança ficam centralizados na
            API FlowGuard.
            """
        ),
    ]
    notebook.setdefault("metadata", {})["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook["metadata"]["language_info"] = {"name": "python", "version": "3.10"}
    NOTEBOOK.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Updated {NOTEBOOK} with {len(notebook['cells'])} cells")


if __name__ == "__main__":
    main()
