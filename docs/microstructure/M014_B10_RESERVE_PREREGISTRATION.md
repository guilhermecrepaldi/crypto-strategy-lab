# M014 — reconstrução B10 F2.5 com reserva OWNER

Pré-registro anterior a qualquer resultado M014. Primeira semana somente.
Autoridade OWNER: conferir a queda na semana inicial com100 USDT, resgatar boa parte
do B10 com otimizações da reserva, avaliar1–7 janeiro e mirar2.000 ciclos diários.
Extensão continua sujeita à aprovação humana específica de cada semana.

## Observação e hipótese

M013 DAY_7 fecha com1 ciclo, O100.00891, R10.00099, equity110.0099, zero releases,
reserva não consumida,6 dias sem ciclo. O bug de BUY obsoleta foi reproduzido e
corrigido. O seletor foi trocado e a elegibilidade inicial de recovery foi adiada
de H1 no B10 para6h no M013. Portanto, não há comparação equivalente que prove
falha do B10 ou limitação da reserva nessa semana.

Pai científico: RRV2_H1_B10_F2.5 /097abdab, não M013 invalidado. M014 recupera
M007 seleção/histerese/reseleção após saída, H1, condição econômica B10 e piso2.5.
Mantém um lote para isolar mecanismo. Até três filas era capacidade máxima, não
obrigação de ocupá-las. Q4 e urgência6/12/18h não são importadas neste estudo.

Mudança financeira explícita:100 operacionais +10 reserva, contra100+5 histórico;
10% do lucro realizado positivo para reserva, contra2%; resto reinvestido. Nenhum
reset/notional fixo/saque. Benefício esperado: ampliar cobertura/reposição de
releases sem desfigurar o seletor. Risco: menos reinvestimento operacional e
mais caixa segregado; reserva maior não cria contraparte nem garante mais ciclos.

## Reutilização e execução

ADOPT autoridades canônicas M007 e RecoveryReserveRuntime para decisões. ADAPT
B10RealityReplay/FrozenB10Decisions por dependências explícitas, defaults históricos
inalterados; ADAPT sizing/ledger Decimal, dust, proteção IOC e escrow da autoridade
HighUptimeExecution. REJECT herdar a urgência M012/M013 ou a seleção M013.
Não criar pipeline paralelo; adaptar runner existente run_high_uptime_recovery.

O predicate B10 mantém config histórica de referência F2.5. Cada probe recebe
inventário/custo/caixa/reserva realmente simulados. Suas transferências teóricas
nunca alteram o ledger real. Settlement usa lucro/perda realmente preenchidos,
funding10% e cobertura exata com piso2.5 protegido; parcial não vira FLAT.
Release tem proteção de preço e escrow. Se não houver execução suportada, permanece
aberta.24h é violação observável, não ordem fictícia ou autorização de early stop.

PerfilB imutável: fila2330544 USDC, latência1179525us, fee zero condicional, regras
e book envelope vinculados pelo hash do spec. Não é reconstrução do L2 histórico
nem certificação de execução Binance. Não diminuir fila/latência para cumprir meta.

## Protocolo e aceitação

Intervalo [2026-01-01,2026-01-08), UTC,2.489.204 trades de replay esperados conforme
evidência anterior, reconfirmar nos arquivos físicos. Warmup31dez separado; ler,
hashear e reconciliar apenas esse prefixo. Nenhum trade de8jan em diante autorizado.
Publicar spec, configuração, revisão e fonte antes do replay; registrar novo M014.
Proibir overwrite de artifacts e múltiplos writers.

Salvar sete fechamentos diários estritos, ledger e checkpoint integral. Contar
BUY integral→SELL integral líquida positiva, sem releases/parciais/tentativas.
Meta >=2.000 EM CADA dia;14.000 na soma é necessário, não suficiente. Reportar
O/R/equity, PnL realizado e marcação, funding/consumo/minR, ciclos, releases,
fills/rejeições por motivo, holding/idle/working time e violações. Tempo com ordem
não deve ser chamado automaticamente de tempo produtivo.

Resultado econômico só após dados completos e auditoria independente:100 ciclos
ordinários determinísticos ou todos se menos, e todos os releases, incluindo
parciais/escrows; amostra insuficiente explicitada. Testes não provam a estratégia.
Final de semana sempre AWAITING_OWNER_APPROVAL, mesmo que meta atingida. Posições,
ordens e capital preservados para eventual continuidade do mesmo modelo/hash.

Comparação com M013 marcada INVALIDATED_TECHNICAL; não serve como controle econômico.
B10 histórico price-path é referência descritiva, não controle de fills. Esta
execução estabelece a base B10 com capital OWNER. Um futuro filtro de admissão
post-only, se motivado pela autópsia, exige nova identidade; não embutir/tunar neste
M014 nem prometer que sua eficácia já foi demonstrada.
