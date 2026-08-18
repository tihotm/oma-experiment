# OMA7 Operational Constitution

Você está trabalhando no projeto **OMA7**.

Este arquivo tem autoridade operacional para o repositório `oma-experiment`.
Se houver conflito entre chat, memória e este arquivo, este arquivo prevalece.

## Missão

OMA7 é a camada mínima acima de coding agents existentes que aumenta autonomia,
confiabilidade e eficiência de missões reais.

Não estamos construindo um novo coding agent.

Não há arquitetura final pré-definida.

## Ordem de decisão

Adote esta ordem sempre que for praticável:

`ADOPT > COMPOSE > ADAPT > BUILD`

Não implemente algo maduro do zero se um donor local já entregar a capacidade
com a mesma semântica ou com adaptação pequena e justificável.

## Método de trabalho

Trabalhe por lotes.

Para cada lote:

`INSPECT -> PLAN -> IMPLEMENT -> TEST -> VERIFY -> DOCUMENT`

Não pule direto para BUILD quando a fronteira arquitetural ou o landscape de
donors ainda não estiverem entendidos.

## Desenvolvimento guiado por evidência

- Faça claims apenas depois de executar testes ou verificar artefatos reais.
- Não declare benchmark, CI, deploy, compatibilidade ou maturidade sem evidência
  executada nesta sessão.
- Separe claramente fato, inferência e hipótese.
- Se algo não foi executado, diga que não foi executado.

## Donors e referências

Os diretórios em `references\` são donors ou referências somente leitura.

- Não editar donors.
- Não commitar em donors.
- Não assumir que donor está atualizado sem ler sua evidência local.
- Preferir reutilização, composição ou adaptação antes de criar código novo.

Donors oficiais para este projeto:

- `references\SWE-bench`
- `references\attestation`
- `references\witness`

## Boundary de uso dos donors

- Inspecione donors antes de qualquer BUILD relevante.
- Identifique primitivas reutilizáveis, dependências, riscos e limites.
- Não copie subsistemas inteiros quando uma primitive menor bastar.
- Documente por que um donor foi adotado, composto, adaptado, apenas
  referenciado ou descartado.

## Git como primitive

Antes de criar identidades complexas, avalie se semântica de Git já cobre a
necessidade:

- path
- content
- tree structure
- executable bit / file mode
- symlink
- submodule pointer

Investigue separadamente:

- untracked files
- ignored files
- case semantics no Windows

Se Git bastar, reutilize Git.

## Invariantes de evidência

Evidence só autoriza acceptance quando:

`same(subject identity)` AND
`same(verification context identity)` AND
`result == PASS`

- FAIL nunca autoriza acceptance.
- UNKNOWN nunca vira PASS implicitamente.
- O verifier não deve alterar o submission congelado.
- Retry do verifier deve reutilizar o mesmo snapshot.

## Escopo explícito do lote atual

Neste lote, a meta é estabelecer a fundação experimental mínima do OMA7 usando
reuso máximo de primitives existentes.

Não adicionar neste lote:

- supervisor LLM
- router
- planner
- swarm
- multi-agent runtime
- memory system
- Temporal
- DBOS
- Restate
- cost-aware controller
- executor selection
- UI

## Capacidades alvo do projeto

As capacidades abaixo devem sair de reuso/composição primeiro:

1. submission snapshot/identity
2. verification-context identity
3. evidence vinculada a subject + verification context
4. evidence applicability
5. verifier operando sobre cópia/snapshot
6. SWE-bench adapter
7. B0 normalized observation
8. B0 qualifier
9. testes adversariais
10. documentação machine-readable de upstream pins

## Donor SWE-bench

Use `references\SWE-bench` como donor oficial de benchmark.

- Não atualizar silenciosamente.
- Reusar preferencialmente `run_instance`, `skip_patch`, `get_eval_report`,
  `tests_status`, `FAIL_TO_PASS`, `PASS_TO_PASS`, reporting, grading, log
  parsers e infra failure classification.
- Não reimplementar grading do SWE-bench.
- Confirmar em teste a semântica de baseline/no-patch com `skip_patch=True` e a
  interação com `prediction["model_patch"]`.

## Donor in-toto Attestation

Use `references\attestation` para avaliar o modelo de:

- subject identity
- evidence statement
- predicate
- provenance

Preferir `Statement`/`subject`/`predicate` do modelo in-toto antes de criar um
formato OMA7 próprio.

## Donor Witness

Use `references\witness` para auditar:

- attestation creation
- verification
- policy/evidence validation
- provenance

Classificar cada capacidade como `ADOPT`, `COMPOSE`, `ADAPT`, `REFERENCE` ou
`BUILD`.

Não integrar o Witness inteiro se apenas uma primitive for necessária.

## CI e testes

- Criar CI mínima e reproduzível para a suíte do OMA7.
- Não executar SWE-bench completo em CI se exigir recursos excessivos.
- Separar testes unit/contract de benchmark real.
- Cobrir testes adversariais para mutações de subject, contexto, config,
  dependências, lockfiles, delete, rename, harness version, dataset revision e
  environment identity.

## Documentação obrigatória

Manter, no repositório canônico, documentação atualizada quando o lote avançar:

- `README.md`
- `docs\REUSE-MATRIX.md`
- `docs\CLAIM-MAP.md`
- `docs\ARCHITECTURE-STATUS.md`
- `docs\LOTE-1-RESULTS.md`
- `protocol\UPSTREAM-PINS-P0.json`
- `protocol\EXPERIMENT-P0.md`

## Entrega e encerramento

- Deixar o working tree limpo ao fim do lote, exceto quando explicitamente
  solicitado de outro modo.
- Não fazer claims de conclusão sem execução real.
- Se houver hard blocker real, documente-o com precisão.
- Ao final, reporte status factual, testes executados e limitações.

