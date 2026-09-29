# UX/UI Continuidade - Central de Ativos V3

Esta revisão alinha a malha visual da Central de Ativos à Central de Indicadores sem alterar backend, APIs ou regras de negócio.

## Ajustes aplicados

- Padding externo da página igualado à Central de Indicadores no desktop.
- Hero da Central de Ativos ajustado para 330px, com a mesma distribuição horizontal, largura da área da personagem, respiro do texto e largura da coluna de métricas.
- Personagem, círculos decorativos, balão, título, subtítulo e texto auxiliar reposicionados/proporcionados seguindo a malha do Hero da Central de Indicadores.
- Cards de métricas do Hero igualados em altura, ícone, gaps e densidade visual aos cards da Central de Indicadores.
- Fundo geral e sombra do Hero harmonizados com o restante do produto.
- Distância entre Hero e seção de lojas ajustada para 16px, igual ao padrão da home de Indicadores.
- Container de lojas passou a usar o mesmo padding do bloco "Indicadores disponíveis".
- Título, subtítulo e badge da seção de lojas ajustados para a mesma hierarquia visual da Central de Indicadores.
- Busca, filtro, contador de resultados e grid receberam espaçamentos mais regulares.
- Cards de loja receberam mais preenchimento interno e altura mínima para melhor equilíbrio visual.
- Breakpoints de 1360px, 1100px e mobile foram harmonizados com os utilizados na Central de Indicadores.
- A tela interna das lojas manteve sua hierarquia anterior; os ajustes de título da home não foram propagados indevidamente aos painéis internos.

## Validação

- Testes Central de Ativos: 3/3 aprovados.
- Testes Central de Indicadores: 9/9 aprovados.
- Build Vite: aprovado (884 módulos transformados).
- Oxlint na feature de Ativos: 0 warnings e 0 erros.

Nenhuma alteração foi feita no backend.
