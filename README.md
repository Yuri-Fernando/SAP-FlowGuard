# 🛡️ SAP FlowGuard

### Python · FastAPI · SQLAlchemy · PostgreSQL · Redis · n8n · OData V2/V4 · Docker · pytest · Ruff

## Status

🟡 **Fundação funcional implementada e testada** nos modos `mock`, `sandbox` e `hybrid` — 7 testes
unitários (regras determinísticas, segurança de escrita *fail-closed*, degradação graciosa do
monitor de n8n sem API key, integridade do notebook end-to-end), CI com lint, testes e build Docker
em todo push/PR. O modo `live` é um ponto de extensão **deliberadamente não implementado**: a
factory de providers levanta `NotImplementedError` explícito, porque um tenant S/4HANA real exige
*communication arrangement*, autenticação e allowlist específicos do cliente — nenhum workflow
finge que uma sandbox pública suporta escrita produtiva. A integração com n8n é somente leitura
(`/healthz`, workflows, histórico de execuções) e os 4 workflows exportados estão `active: false`
por padrão; eles nunca foram executados contra uma instância n8n real, apenas validados
estruturalmente (`scripts/validate_workflows.py`). A API não tem autenticação de usuário final —
é uma base de portfólio local, não um serviço de produção exposto à internet (ver
[`docs/security.md`](docs/security.md)).

## Descrição / Contexto

Empresas que operam em SAP S/4HANA costumam ter FI (contabilidade), SD (vendas) e MM (compras)
tecnicamente integrados dentro do ERP, mas **operacionalmente desconectados** na prática: uma
fatura de venda (*billing document*) pode nunca gerar o lançamento contábil correspondente, uma
nota fiscal de fornecedor pode chegar com preço fora da ordem de compra, um lançamento duplicado
pode escapar de uma conciliação manual feita em planilha. Esses são exatamente os pontos onde
dinheiro, prazo de fechamento contábil ou compliance fiscal ficam em risco — e onde, normalmente,
alguém só descobre o problema dias depois, numa reconciliação manual.

**SAP FlowGuard** é uma torre de controle que lê documentos de negócio do SAP (pedido de venda,
fatura, pedido de compra, nota de fornecedor, lançamento contábil), aplica regras determinísticas
de correlação cross-módulo (Order-to-Cash, Procure-to-Pay, Record-to-Report), transforma qualquer
inconsistência detectada em uma exceção auditável, e só permite uma ação corretiva de volta ao SAP
depois que todas as travas de segurança — flag de escrita, aprovação humana vinculada à ação exata,
idempotência — forem satisfeitas. Nenhum LLM participa da decisão: o motor de regras é 100%
determinístico e o fluxo de escrita é *fail-closed* por padrão.

O princípio central do projeto é **não depender de um tenant S/4HANA pago para ser demonstrado**.
Por isso ele roda em três modos combináveis: contra um **Mock SAP local** que simula respostas
OData V2/V4 com paginação, CSRF e ETag reais; contra a **sandbox pública do SAP Business
Accelerator Hub** (somente leitura); ou em modo **híbrido**, lendo da sandbox real e escrevendo no
mock local — a configuração pensada para demonstração gratuita e seca-mas-honesta do fluxo
completo, sem nunca arriscar um writeback real.

## Objetivo

- Correlacionar documentos SAP entre módulos (SD × FI, MM × FI) e detectar exceções que uma
  reconciliação manual demoraria dias para encontrar;
- Manter o motor de decisão 100% determinístico e auditável — nenhuma IA decide nada financeiro;
- Tratar escrita de volta ao SAP como operação privilegiada: desligada por padrão, liberada por
  flag de ação específica, condicionada a aprovação humana vinculada à ação exata solicitada, e
  protegida por chave de idempotência contra replay;
- Demonstrar os três modos de integração SAP (mock / sandbox / híbrido) sem exigir nenhuma
  credencial paga, e deixar o modo `live` como extensão explícita, não como simulação disfarçada;
- Expor todo o histórico de exceções, aprovações e auditoria por uma API versionável e por um
  dashboard executivo, com orquestração/agendamento isolado em n8n — sem nenhuma regra de negócio
  ou credencial sensível dentro dos workflows exportados.

## Arquitetura

```text
                 ┌─────────────────────────────────────────────┐
                 │               SAP_MODE (.env)                │
                 │     mock   │   sandbox   │   hybrid   │ live │
                 └──────┬─────────────┬────────────┬──────┬─────┘
                        │             │            │      │
                        ▼             ▼            ▼      ▼
                 ┌────────────┐ ┌───────────────┐  │  NotImplementedError
                 │  Mock SAP  │ │ SAP Business   │  │  (ponto de extensão
                 │  (FastAPI) │ │ Accelerator Hub│  │   explícito)
                 │ OData V2/V4│ │   (somente     │  │
                 │ CSRF · ETag│ │    leitura)    │  │
                 └─────┬──────┘ └───────┬────────┘  │
                       │                │            │
                       └───────┬────────┘            │
                               ▼                      │
                     SapProvider (abstração)  ◄───────┘
              mock · sandbox · hybrid (lê sandbox, escreve mock)
                               │
                               ▼
                 mapeamento OData → modelos canônicos
            (SalesOrder · BillingDocument · PurchaseOrder ·
             SupplierInvoice · JournalEntry)
                               │
                               ▼
                     RulesEngine (determinístico)
              O2C (SD001/SD002/SD004/SD005/CROSS004)
              P2P (MM003/MM004/MM005/MM007)
              FI  (FI001/FI002)
                               │
                               ▼
         deduplicação por fingerprint + persistência (PostgreSQL)
         flowguard_exceptions · flowguard_approvals ·
         flowguard_audit_events · flowguard_idempotency
                               │
                 ┌─────────────┼──────────────┐
                 ▼             ▼              ▼
          FlowGuard API   ApprovalService   WritebackService
          (FastAPI)       (fila humana)     (6 gates em cascata,
                                              ver Segurança de escrita)
                 │             │              │
                 └─────┬───────┴──────┬───────┘
                       ▼              ▼
                n8n (agendamento    Dashboard executivo
                /orquestração,      (exceções, risco,
                sem regra de        aprovações, saúde
                negócio embutida)   do n8n)
```

Em `hybrid`, leituras vão para a sandbox SAP real e escritas são explicitamente roteadas para o
Mock SAP local — nunca o contrário.

## Funcionamento

1. `POST /runs/o2c` (ou `/runs/p2p`, `/runs/fi`) dispara o `MonitorService`, que busca os
   documentos correspondentes no provider ativo e gera um `correlation_id` se nenhum for enviado
   via header `X-Correlation-ID`;
2. os payloads OData são convertidos para os modelos de domínio canônicos por `mappers.py`
   (parsing defensivo de `Decimal` e datas, incluindo o formato legado `/Date(ms)/`);
3. o `RulesEngine` aplica as regras determinísticas do processo (O2C, P2P ou FI) e produz zero ou
   mais `ExceptionRecord`, cada um com regra, severidade, valor em risco e evidência;
4. as exceções são deduplicadas por *fingerprint* (hash de regra + documento + status) antes de
   persistir — reexecutar o mesmo monitor não duplica a mesma exceção — e o evento é registrado em
   auditoria (`MONITOR_COMPLETED`);
5. uma exceção com `approval_required=True` pode receber uma solicitação de aprovação
   (`POST /approvals`); um humano decide (`POST /approvals/{id}/decision`), e a decisão também é
   auditada;
6. uma tentativa de escrita de volta ao SAP (`POST /writebacks`) só é executada se passar pelos 6
   portões descritos em **Segurança de escrita** — caso contrário a API responde `403` e o
   provider SAP nunca é chamado;
7. o dashboard (modo simples ou modo "n8n monitor") consulta `/exceptions`, `/approvals` e
   `/health` da API, mais `/healthz` do n8n, e apresenta tudo em uma única tela, com degradação
   graciosa quando a API Key do n8n não está configurada.

## Modos de execução (`SAP_MODE`)

| `SAP_MODE` | Leitura | Escrita | Uso pretendido |
|---|---|---|---|
| `mock` | Mock SAP local | Mock SAP local, sob os gates de escrita | demo completa sem custo, sem credencial |
| `sandbox` | SAP Business Accelerator Hub | sempre recusada (provider é somente leitura) | validar leitura/contrato contra um SAP real |
| `hybrid` | SAP Business Accelerator Hub | Mock SAP local, sob os gates de escrita | demo principal de portfólio: lê real, escreve seguro |
| `live` | específico do tenant | específico do tenant, sob os gates de escrita | extensão futura para um ambiente de cliente real |

Para `sandbox`/`hybrid`, defina `SAP_API_KEY` e copie a *base URL* vigente na tela **Try Out** da
API escolhida no Business Accelerator Hub. A disponibilidade de endpoints varia por API publicada.

## Regras de negócio implementadas

O motor (`src/flowguard/rules/engine.py`) é explicitamente documentado no código como
determinístico — nenhuma IA participa da decisão.

**Order-to-Cash (O2C)**

| Regra | Módulo | Severidade | Dispara quando |
|---|---|---|---|
| `SD001` | SD | MEDIUM | pedido de venda sem nenhum billing document associado |
| `SD002` (`BILLING_WITHOUT_FI`) | CROSS | HIGH / CRITICAL | billing sem lançamento contábil e não cancelado |
| `CROSS004` | CROSS | HIGH | billing referencia um pedido de venda inexistente |
| `SD005` | SD | HIGH | moeda do billing diverge da moeda do pedido de venda |
| `SD004` | SD | HIGH | valor do billing diverge do valor do pedido de venda |

**Procure-to-Pay (P2P)**

| Regra | Módulo | Severidade | Dispara quando |
|---|---|---|---|
| `MM003` | MM | HIGH | nota de fornecedor sem pedido de compra correspondente |
| `MM004` | MM | HIGH | nota bloqueada há ≥ 3 dias sem liberação |
| `MM005` (`PO_INVOICE_PRICE_VARIANCE`) | MM | HIGH / CRITICAL | variância de preço nota × PO acima da tolerância (2% por padrão) |
| `MM007` | MM | CRITICAL | nota duplicada (mesma assinatura fornecedor + valor + moeda + data) |

**Record-to-Report (FI)**

| Regra | Módulo | Severidade | Dispara quando |
|---|---|---|---|
| `FI001` | FI | CRITICAL | lançamento contábil duplicado (mesma assinatura) |
| `FI002` | FI | HIGH | valor do lançamento acima do limite crítico (R$ 100.000 por padrão) |

Regras marcadas `approval_required=True` (`MM004`, `MM005`, `MM007`, `FI001`, `FI002`) nunca podem
virar um writeback automático — exigem aprovação humana vinculada à ação exata.

## Segurança de escrita

Toda escrita de volta ao SAP (`WritebackService.execute`) passa por 6 portões em cascata, em
ordem, antes de tocar o provider:

1. **Idempotência** — se a `idempotency_key` informada já tem um resultado salvo, a resposta
   anterior é replicada (`idempotent_replay: true`) e o provider SAP **não é chamado de novo**;
2. **Chave geral** — `ENABLE_SAP_WRITE=true`, senão a requisição é recusada;
3. **Flag por ação** — cada ação exige sua própria flag (`post_journal_entry` →
   `ALLOW_FI_POSTING`, `cancel_billing_document` → `ALLOW_BILLING_CANCEL`,
   `release_supplier_invoice` → `ALLOW_INVOICE_RELEASE`);
4. **Aprovação humana** — se `REQUIRE_HUMAN_APPROVAL=true` (padrão), é exigido um `approval_id` de
   uma aprovação existente, no estado `APPROVED`, **cuja ação registrada seja idêntica** à ação
   solicitada no writeback;
5. **Protocolo SAP** — o provider precisa satisfazer CSRF (token de uma via) e ETag/`If-Match`
   antes de aceitar a escrita;
6. **Auditoria** — todo resultado (sucesso ou falha) é gravado em `flowguard_audit_events` com
   `correlation_id`, ator e payload serializado.

Qualquer violação resulta em `403` na API e em `SapWriteError` internamente — nunca em uma chamada
silenciosa ao provider. Um teste dedicado (`tests/unit/test_write_safety.py`) usa um provider que
levanta `AssertionError` se `write()` for chamado, provando que a configuração padrão nunca chega
a acionar o SAP. Em um tenant real, use identidades técnicas separadas para leitura e escrita e
nunca inclua credenciais SAP dentro de um export de workflow n8n (ver
[`docs/security.md`](docs/security.md)).

## Mock SAP: cenários sintéticos

O Mock SAP (`mock_sap/`) simula paginação OData V2 (`d.results`/`__next`) e V4
(`value`/`@odata.nextLink`), fluxo de CSRF real (`GET /mock/csrf` → token de uma via),
precondição ETag/`If-Match`, e injeção de falha via headers (`x-mock-error`,
`x-mock-latency-ms`). Treze cenários trocáveis em runtime (`POST /mock/scenario/{nome}`):

`normal` · `blocked_invoice` · `duplicate_invoice` · `billing_without_fi` · `po_price_variance` ·
`quantity_variance` · `late_billing` · `duplicate_journal` · `cross_module_reference_break` ·
`api_timeout` · `odata_pagination` · `csrf_failure` · `etag_conflict`.

## Tecnologias

- **Backend / API:** Python 3.10+, FastAPI, Pydantic Settings, Uvicorn;
- **Domínio e regras:** modelos canônicos Pydantic, motor de regras determinístico próprio;
- **Persistência:** SQLAlchemy 2.x sobre PostgreSQL (produção/compose) ou SQLite (local sem
  Docker), schema criado em runtime, deduplicação por fingerprint, idempotência e auditoria
  dedicadas;
- **Integração SAP:** `httpx` assíncrono, abstração de provider própria (`mock` / `sandbox` /
  `hybrid` / `live`), OData V2 e V4, CSRF, ETag;
- **Orquestração:** n8n (workflows versionados, inativos por padrão, sem regra de negócio
  embutida);
- **Infraestrutura local:** Docker Compose (PostgreSQL, Redis, Mock SAP, API, dashboard, n8n);
- **Qualidade:** pytest + respx, Ruff (`E`, `F`, `I`, `UP`, `B`, `SIM`), GitHub Actions (lint +
  testes + build Docker em todo push/PR).

## Quick start (modo mock, sem credencial SAP)

```powershell
Copy-Item .env.example .env
docker compose up --build
```

| Serviço | URL |
|---|---|
| API FlowGuard (docs) | <http://localhost:8000/docs> |
| Dashboard | <http://localhost:8501> |
| Mock SAP (docs) | <http://localhost:8080/docs> |
| n8n | <http://localhost:5678> |

O dashboard sempre mostra saúde da API/SAP, exceções, aprovações e risco financeiro. Para também
mostrar os workflows reais do n8n e as 30 execuções mais recentes, crie uma chave em **Settings >
n8n API** e defina-a somente no `.env` local:

```dotenv
N8N_API_KEY=substitua-por-sua-chave-local
```

Sem a chave, o dashboard continua checando `/healthz` do n8n normalmente e degrada com uma
mensagem explicativa, sem erro (ver [`docs/n8n-monitor.md`](docs/n8n-monitor.md)). O notebook
guiado de ponta a ponta está em
[`output/jupyter-notebook/sap-flowguard-end-to-end.ipynb`](output/jupyter-notebook/sap-flowguard-end-to-end.ipynb).

Executar o cenário principal sem depender do n8n:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/runs/o2c
Invoke-RestMethod http://localhost:8000/exceptions
```

Trocar o cenário sintético ativo:

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/mock/scenario/po_price_variance
Invoke-RestMethod -Method Post http://localhost:8000/runs/p2p
```

## Desenvolvimento local

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python scripts/validate_workflows.py
```

O validador de workflows confere apenas a estrutura dos JSON exportados (chaves obrigatórias,
nomes/ids de nó únicos); a verificação de execução real contra uma instância n8n está documentada
em [`n8n/README.md`](n8n/README.md), não automatizada neste estágio.

## Estrutura do repositório

- `src/flowguard/`: domínio, regras, providers SAP, serviços e persistência;
- `mock_sap/`: simulador de comportamento S/4HANA e cenários sintéticos;
- `apps/api/`: API de orquestração (FastAPI);
- `apps/dashboard/`: dashboard executivo e monitor de n8n;
- `n8n/workflows/`: exports versionados prontos para importação, inativos por padrão;
- `sql/postgres/`: script de criação do schema `flowguard` (as tabelas de negócio são criadas em
  runtime pelo SQLAlchemy);
- `docs/`: arquitetura, segurança, guia de demo e monitor de n8n;
- `scripts/`: validação de workflows e geração do notebook end-to-end;
- `tests/unit/`: regras determinísticas, segurança de escrita, monitor de n8n, notebook.

A definição técnica completa do programa permanece em
`SAP_FlowGuard_Definicao_Completa_Programa_2026-10-02.txt`.

## Testes

Sete testes unitários cobrem os pontos mais sensíveis do sistema, não a totalidade da superfície:

- `test_rules.py` — regras `BILLING_WITHOUT_FI`, `PO_INVOICE_PRICE_VARIANCE` e detecção de nota
  duplicada (`MM007`);
- `test_write_safety.py` — confirma que, na configuração padrão, o provider SAP **nunca é
  chamado** para uma escrita, com um provider de teste que falha caso `write()` seja invocado;
- `test_dashboard_monitor.py` — degradação graciosa do monitor de n8n sem API key e leitura
  correta de workflows/execuções com API key;
- `test_notebook.py` — garante que o notebook end-to-end é válido, compilável e sem saída
  pré-gravada.

Ainda não há testes de integração, contrato ou end-to-end executados contra a stack Docker
completa — ponto explícito de evolução futura, não uma lacuna escondida.

## Documentação adicional

- [`docs/architecture.md`](docs/architecture.md) — fronteiras de decisão, providers e próximos
  incrementos planejados (probes de capacidade, adapter SOAP, locks/DLQ via Redis, métricas);
- [`docs/security.md`](docs/security.md) — modelo *fail-closed* completo e recomendações para um
  tenant real;
- [`docs/demo-guide.md`](docs/demo-guide.md) — roteiro reproduzível de demonstração dos cenários
  O2C e P2P;
- [`docs/n8n-monitor.md`](docs/n8n-monitor.md) — os dois níveis de monitoramento do dashboard.

## Licença

MIT. Nomes de produto e marcas da SAP pertencem à SAP. Este repositório contém apenas dados
sintéticos e não concede acesso ou licenciamento a sistemas SAP.
