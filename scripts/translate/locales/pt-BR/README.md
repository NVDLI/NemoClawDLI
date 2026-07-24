# Perfil de localização pt-BR

Este perfil não é um dicionário de substituição. Ele registra como o curso deve soar para
estudantes e profissionais de software no Brasil e quais problemas uma validação estática
consegue detectar sem fingir que revisa a qualidade de uma tradução inteira.

## Princípio

Preserve a ideia, o nível técnico e a sequência pedagógica. Não preserve a forma da frase em
inglês quando ela produz uma construção artificial em português. Código, identificadores,
nomes de produto, URLs e o JSON `skill-meta` continuam canônicos.

Textos dentro de SVGs também fazem parte da experiência. A versão pt-BR usa sobreposições
esparsas que preservam a geometria e traduzem rótulos visíveis e descrições acessíveis. Revise
essas figuras renderizadas em tema claro e escuro; textos mais longos podem exigir rótulos mais
concisos ou ajustes tipográficos sem alterar o conceito.

## Vocabulário NVIDIA

O arquivo `profile.json` cita páginas públicas da NVIDIA Brasil. Elas sustentam escolhas como
`IA baseada em agentes`, `agente de pesquisa profunda`, `geração aumentada por recuperação`,
`implantação`, `segurança em tempo de execução` e `aplicação de políticas`.

O perfil também cruza documentação técnica pt-BR da Microsoft e da AWS. Essas fontes ajudam a
distinguir termos que parecem sinônimos, mas cumprem papéis diferentes: `runtime` nomeia um
componente, enquanto `em tempo de execução` descreve quando algo ocorre; `workflow` nomeia a
abstração do curso, enquanto `fluxo de trabalho` cabe em prosa geral. A documentação brasileira da
NVIDIA mantém empréstimos como `runtime`, `stack`, `guardrails` e `sandbox`. Não os traduza de
forma mecânica, nem os espalhe onde uma expressão portuguesa é mais clara.

Termos de interface consolidados entre desenvolvedores, como `workflow`, `framework`, `runtime`,
`sandbox` e `stack`, podem permanecer em inglês. Forçar traduções literais nesses casos piora a
leitura e dificulta a ligação entre o curso, o código e a documentação dos produtos.

## O que a validação bloqueia

- página aceita como atual com `lang` diferente de `pt-BR`;
- parágrafo ou rótulo evidente ainda em inglês;
- tradução literal conhecida por soar artificial ou mudar o conceito;
- contrato `skill-meta` diferente do contrato em inglês;
- arquivo localizado que perdeu IDs ou dependências estruturais do original;
- hash de origem alterado depois da última revisão;
- código ou ativo duplicado dentro do overlay de idioma.

## O que exige julgamento humano

Cadência, naturalidade, precisão conceitual e adequação ao público não cabem em uma lista de
palavras. O Studio de localização reduz o custo dessa revisão: mostra as duas páginas, o hash que
mudou, os sinais encontrados e o comando exato para aceitar uma nova base depois da leitura.

Leia o parágrafo inteiro depois de traduzir. Uma frase pode passar pelo glossário e ainda falhar por
concordância, regência, sujeito ambíguo, título traduzido literalmente ou sequência pedagógica
quebrada. Execute também `prose_variety.py --page` sobre o overlay: os detectores estruturais de
frases longas, repetições e cadência funcionam em grande parte sem depender do idioma. Corrija o
problema de composição; não troque apenas a pontuação para silenciar o sinal.

Um rascunho gerado não é uma página revisada. Primeiro gere e refine com
`translate_html_segments.py`; depois leia os blocos completos no Studio. Corrija concordância,
calques e termos técnicos no contexto. Quando um defeito puder reaparecer em outra página,
registre a expressão específica em `profile.json`. Só então aceite o hash da origem.

`shell_translations.json` traduz as perguntas e os enquadramentos dos blocos de detalhe. No build,
`locale_projection.py` combina essas traduções e a prosa revisada com a estrutura completa da
página canônica atual. Um novo controle sem tradução deve bloquear a validação.

```bash
python3 scripts/validation/localization_audit.py --locale pt-BR
python3 scripts/validation/localization_audit.py --locale pt-BR --self-test
python3 scripts/translate/translate_svg_text.py web/nemoclaw/assets/figures/FIGURE.svg --no-api
```
