# CryptoChange local operator dashboard

O cockpit local é uma camada operacional sobre a autoridade científica vigente. Ele lê
`docs/research/CURRENT_STATE.md` e o `Mxxx_MODEL_SPEC.json` correspondente; não altera
thresholds, modelo ou matemática da estratégia.

## Instalação e início

No Windows, na raiz do repositório:

```powershell
uv sync
uv run crypto-lab operator-dashboard
```

O servidor mostra e abre `http://127.0.0.1:8765`. Outra porta pode ser escolhida com
`--port 9000`. O bind é sempre `127.0.0.1`; `0.0.0.0` não é aceito. Para validar sem
credenciais ou rede Binance:

```powershell
uv run crypto-lab operator-dashboard --demo
```

## Configurar e testar Binance

1. Em **Binance connection**, informe API key e secret.
2. Use **Save locally**. Os campos são imediatamente limpos.
3. Use **Test connection** para validar rede, server time, clock skew, conta assinada,
   permissões, saldos e acesso a `USDCUSDT`.

O teste não cria ordens. A credencial completa é protegida pelo Windows DPAPI para o usuário
logado no arquivo local ignorado `runtime/operator-credentials.dpapi`. SQLite e o journal
recebem somente metadata e dados redigidos. Não existe fallback plaintext. O painel sinaliza
como crítico se a chave tiver permissão de saque; o software não possui endpoint de saque.

Para remover a credencial, use **Delete**. **Disconnect** encerra apenas a visão privada e
mantém o vault local. O status não sensível também está disponível em:

```powershell
uv run crypto-lab credentials-status
uv run crypto-lab operator-status
```

## Play, stop e recuperação

**PLAY** abre o pre-flight e só oferece **Start Shadow**. A primeira entrega não contém
transporte de ordem e mantém `TRADING_ENABLED=false`; escolher LIVE pela API falha fechado.

**STOP** é graceful: desabilita novas entradas, preserva o estado e termina em
`STOPPED_SAFE`. **Emergency stop** exige digitar `CONFIRM STOP`, cancela somente trabalho
SHADOW e preserva holdings; ele não inventa liquidação.

Se a aplicação cair enquanto o estado persistido era `RUNNING`, o próximo início fica em
`RECOVERING`, não reinicia o bot e bloqueia PLAY até reconciliação explícita. Nesta entrega
SHADOW-only, reconciliação certifica que não pode existir ordem Binance originada pelo
cockpit. Uma entrega futura deve comparar conta, saldos e ordens antes de qualquer gate LIVE.

## Dados e segurança local

- Estado: `runtime/operator.sqlite3` (não versionado).
- Eventos: `runtime/operator-events.jsonl` (não versionado e redigido).
- Credenciais: blob DPAPI current-user (não versionado).
- Sem cloud, analytics, CDN, Sentry ou database remoto.
- CSP, Host/Origin estritos, sessão HttpOnly e token CSRF protegem mutações locais.
- O bot assistant é somente leitura (`CHAT_ACTIONS=READ_ONLY`).

Pare o servidor com `Ctrl+C`. LIVE só poderá existir após outra autorização OWNER explícita,
outro gate de implementação/revisão e reconciliação privada completa.
