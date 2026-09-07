# Arquitetura do operador M007 — gate 1

## Responsabilidades canônicas

| Responsabilidade | Autoridade / situação |
| --- | --- |
| Configuração e seleção científica | `microstructure/serial_replay.py`: M007 existente, sem cópia ou alteração. |
| Hash, modo, banca inicial, estados | `microstructure/operator.py`: contrato pequeno, puro e fail-closed entregue agora. |
| Replay histórico, tape e contabilidade teórica | Fluxos existentes; nenhuma nova execução neste milestone. |
| Streaming público, persistência e runtime shadow | Prompt 2, ainda não implementados. Reutilizar contratos adequados após inspecionar consumidores. |
| Book/L2 e evidência de executabilidade | Prompt 3, ainda não implementados para este operador. |
| Ordens e reconciliação Binance | Prompt 4+, ausentes/bloqueados. Binance será autoridade de fills reais, nunca o seletor. |

`PassiveExecutionSimulator` existente é legado ligado ao experimento S0/FDUSD, não autoridade
econômica M007. Não executá-lo, copiar sua estratégia ou criar campanha FDUSD paralela.

O módulo novo não é outro motor de estratégia: não contém ranking, scanner, loop de eventos,
cliente de exchange, subprocesso, banco, carregador de secrets ou endpoint de ordens. Define
somente o contrato operacional ainda ausente. As mesmas identidades/estados deverão ser
reutilizados nos passos seguintes, sem backends permanentes V2 ou cópias do M007.

## Decisão Research-First

| Decisão | Referência e aplicação |
| --- | --- |
| ADOPT | `dataclass(frozen=True, slots=True)`, Enum e MappingProxyType da biblioteca padrão para contrato tipado sem dependência nova. |
| ADAPT | `SerialModelConfig` Pydantic e hash já usados pela campanha; derivar M007 e revalidar payload/hash/IDs. |
| BUILD | Somente o gate SHADOW_ONLY e topologia contratual, sem autoridade anterior equivalente. |
| REJECT | Framework de trading, harness LLM, outro seletor, dependência externa e adapter de ordens neste estágio. |

Documentação primária consultada:
[dataclasses](https://docs.python.org/3/library/dataclasses.html) e
[Pydantic models](https://docs.pydantic.dev/latest/concepts/models/).
`frozen` não garante imutabilidade profunda de objetos aninhados nem segurança contra código
hostil. `model_copy(update=...)` não é fronteira de validação. Por isso o contrato armazena
somente valores imutáveis, não aceita configuração científica arbitrária e verifica novamente
a autoridade em cada acesso. Nenhum código externo foi copiado ou dependência adicionada.

## Separação de evidências

Configuração científica → intenção → price-touch teórico não implica ordem/fill. No próximo
gate, o stream deverá carregar timestamp, sequência, preço/quantidade e contexto verificáveis;
o operador usará apenas prefixos causais. Um ledger shadow deve identificar explicitamente
`EXECUTABLE_FILL_UNKNOWN`. Book futuro também não provará fill real sem confirmação Binance.

Hash de estratégia ≠ SHA de implementação ≠ hash de dataset ≠ identidade da sessão. Todos
precisam ser associados no futuro journal. Dinheiro permanece Decimal/fixed-point no motor
canônico; contagem e state machine serial não são movidas para GPU.

## Contrato de recuperação a implementar no gate seguinte

Uma única instância por identidade; checkpoint e journal idempotentes, com estado econômico,
intents, faixa congelada, hash, SHA, janela causal, cursor e âncora de decisão. Boot deve
reconciliar antes de agir. Não existe fallback que apague estado inconsistente ou crie banca
nova. Operador recém-iniciado recebe 100 USDT teóricos; restart restaura exclusivamente sua
sessão. Interrupções não liquidam posição. Reenvio incerto de ordens futuras é proibido sem
consulta/reconciliação. Persistência e testes de crash **ainda pendentes**, não entregues aqui.

## Gates e segurança

1. Atual: freeze M007, contrato e state machine; checks, commit e push; **parar**.
2. Futuro: SHADOW público sem ordens, armazenamento, recovery, single-instance e dashboard.
3. Futuro: coleta L2 e estudo de execução, sem alterar M007.
4. Futuro: Testnet segregada, somente após passos anteriores e continuação autorizada.
5. Futuro: readiness sem ordens; gate financeiro de alocação máxima de 100 USDT.
6. Futuro: live somente por autorização explícita posterior e readiness aprovado. Saques,
   margem, futuros, alavancagem e aumento automático para 1.000 USDT continuam proibidos.

Neste gate `OperatorMode.TESTNET` e `.LIVE` existem apenas para rejeição explícita. Nenhuma
flag ou variável de ambiente habilita trading. Não acessar conta/keys, Testnet/live ou partições
VALIDATION/LOCKED_TEST. O novo protocolo suspende nova evolução Mxxx; M010 histórico permanece
preservado sem uso no operador. Não conectar sequer market data neste milestone.

## Verificação entregue

`tests/test_m007_operator.py` cobre configuração/hash/identidade, ausência de herança de capital,
imutabilidade normal e detecção de adulteração, cópias Pydantic, bloqueio TESTNET/LIVE/env,
negação incondicional de ordens e topologia. A implementação não possui efeitos de rede ou
persistência. A revisão científica foi delegada efetivamente a `gpt-6-astra`; Python executa
as verificações. Não houve novo experimento nem nova conclusão de rentabilidade.
