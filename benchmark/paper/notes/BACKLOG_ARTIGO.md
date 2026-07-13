# Backlog — Finalização do Artigo (IC)

**Prazo:** sexta-feira 12/06/2026 · **Disponibilidade:** tardes de seg→sex (5 sessões)
**Estado:** dados/experimentos ~prontos; falta consolidar narrativa, escrever e formatar.

---

## 0. Decisões TRAVADAS ✅

- ✅ **Congresso-alvo:** **SIBGRAPI** (Conference on Graphics, Patterns and Images).
  - Formato **IEEE two-column**; full paper tipicamente **até 8 páginas** (confirmar limite exato no CFP do ano).
  - Template: IEEE Conference (LaTeX) no **Overleaf** (`IEEEtran`, opção `conference`). SIBGRAPI normalmente exige PDF anônimo p/ revisão double-blind → **omitir nomes/afiliação na submissão**.
  - Implica **ser conciso**: ~**4–6 figuras** e **1–2 tabelas** no total.
- ✅ **Idioma:** **Inglês.**
- ✅ **Quem escreve:** **Claude redige os rascunhos** de cada seção (em EN); **você revisa/ajusta**.
- ✅ **Estatística (Wilcoxon + IC):** só **se sobrar tempo** na sexta (bônus, não bloqueia).
- ✅ **Escopo da história:** benchmark **cross-domain** (3 bases: Oral H&E, NuInsSeg H&E, IHC) avaliado **pixel-a-pixel (protocolo do professor, V1/V2)** + **borda (iftEvalBR do lab)**, em bases **held-out** → conclusão: *não há vencedor universal; o ranking depende da coloração/domínio e da métrica.*

---

## ⭐ REGRA PERMANENTE DO ARTIGO

**Todos os gráficos/tabelas usam o Cellpose SEM a função de perda (`flow_threshold=0`)** — o filtro de erro que descarta células. Motivo: comparação mais justa (sem o pós-filtro proprietário do Cellpose) e curva PR limpa/monotônica. Qualquer figura nova ou regenerada DEVE seguir isso.

Status de conformidade:
- ✅ Oral pixel (`pr_pixel_oral_v1_noflow.png`), Oral borda, NuInsSeg borda — já no-flow
- ⏳ NuInsSeg pixel, IHC pixel — recalcular Cellpose flow=0 (pendente)
- ⏳ IHC borda — rodar (com Cellpose flow=0)

## 1. Contribuição central (o "gancho" do artigo)

> Benchmark **justo (held-out)** de 4 segmentadores de núcleos (Cellpose-SAM, CellViT-SAM-H, PathoSAM, InstanSeg) em **3 datasets** de coloração diferente, sob **métricas pixel-a-pixel e de borda**. Achado: **o "melhor modelo" inverte com o domínio** — Cellpose vence em H&E; CellViT vence em imuno-histoquímica — e **muda com a métrica**. A maioria dos papers compara na base de treino (PanNuke); nós evitamos esse viés.

---

## CRONOGRAMA POR TARDE

### 🗓️ SEGUNDA — Consolidar resultados e travar a história
- [x] Congresso-alvo definido: **SIBGRAPI** (IEEE two-column, ~8 págs, double-blind).
- [ ] Criar projeto no **Overleaf** com template **IEEEtran (conference)** e esqueleto das seções (anônimo).
- [ ] Finalizar a **sweep de borda da NuInsSeg** (rodando) → regenerar `boundary_pr_curve_nuinsseg_noflow.png` completo (4 curvas).
- [ ] Montar a **tabela-mestra de resultados**: 3 bases × 4 modelos × F1 (pixel V1) + melhor limiar. (já temos os números)
- [ ] **Selecionar 6–8 figuras finais** do artigo (matar o resto das 38):
      - Curva PR pixel V1 das 3 bases (oral, NuInsSeg, IHC)
      - Tabela/heatmap do ranking cross-domain
      - Curva de borda (BP×BR) oral + NuInsSeg
      - Overlay diagnóstico (GT × modelos) — mostra detecção vs precisão
      - (opcional) saturação do CellViT (`cellvit_prob_histogram.png`)
- [ ] Atualizar **FINDINGS.md** com o bloco cross-domain (hoje só tem oral/instância).

### 🗓️ TERÇA — Materiais e Métodos (a parte mais "mecânica")
- [ ] **Datasets:** Oral epithelium (100 ROIs, H&E), NuInsSeg (665 patches, 31 órgãos, H&E), IHC_TMA (266, imuno). Tamanhos, coloração, origem, e **justificar held-out** (nenhum modelo treinou neles; por que NÃO usamos PanNuke).
- [ ] **Modelos:** versões e config (Cellpose-SAM `cpsam`; CellViT-SAM-H; PathoSAM ViT-L untiled; InstanSeg brightfield_nuclei). Knobs varridos por modelo.
- [ ] **Métricas/protocolo:** pixel V1 (acerto=TP) e V2 (acerto=TP+TN); borda iftEvalBR (r=2); instância F1/IoU@0.5; pooled vs macro. Limiar 0.1–0.9.
- [ ] **Reprodutibilidade:** hardware (GPU), libs, sweep de limiar.

### 🗓️ QUARTA — Resultados (texto + figuras)
- [ ] Escrever a seção em volta das tabelas/figuras travadas.
- [ ] **Headline:** inversão de ranking por domínio (H&E→Cellpose; IHC→CellViT). Tabela das 3 bases.
- [ ] Sub-achados: saturação do CellViT (limiar inerte), tiling do PathoSAM (Q8), InstanSeg conservador, Cellpose sem função de perda (curva limpa, mesmo F1).
- [ ] Borda: BR parecido entre todos; BF separa pelo Cellpose (precisão de contorno).
- [ ] Inserir figuras com **legendas** e numeração.

### 🗓️ QUINTA — Introdução, Trabalhos Relacionados, Discussão, Conclusão, Resumo
- [ ] **Introdução:** problema (qual modelo usar p/ núcleos em histopatologia), motivação clínica, lacuna (benchmarks viesados pela base de treino).
- [ ] **Trabalhos relacionados:** os 4 modelos + benchmarks (PanNuke/CellViT SOTA, Cellpose-SAM generalização) + a ressalva do vazamento de treino.
- [ ] **Discussão:** a escolha da métrica muda o vencedor; não há modelo universal; justiça via held-out; limitações (n, sem patologista revisando orphans/Q4, IHC fora de domínio).
- [ ] **Conclusão** + **Resumo/Abstract** (escrever por último).
- [ ] **Referências:** já temos Hörst, Graham, Yeung; **adicionar** papers dos datasets (NuInsSeg/Nature Sci Data, MoNuSeg), Cellpose-SAM, PathoSAM/micro-sam, InstanSeg.

### 🗓️ SEXTA — Polimento e entrega
- [ ] (Se decidido) **Estatística:** Wilcoxon pareado entre modelos por ROI + IC. *[risco: pode não dar tempo — ver seção Riscos]*
- [ ] Revisão de consistência: **números do texto == números das tabelas/figuras**.
- [ ] Formatar no template, checar qualidade/resolução das figuras (300 dpi), legendas, citações.
- [ ] Revisão ortográfica/gramatical final.
- [ ] Exportar PDF e **entregar**.

---

## 2. Lacunas conhecidas / riscos (decidir como tratar)

| Item | Status | Decisão |
|---|---|---|
| Estatística (Wilcoxon + IC) | NÃO feito | obrigatório? se sim, agendar quinta/sexta cedo |
| Borda na IHC | NÃO rodado | incluir? (precisa rodar sweep ~1h) ou citar como trabalho futuro |
| Q4 (orphans = núcleos reais ou FP?) | aberto | tratar **qualitativamente** com a figura de overlay; revisão por patologista = trabalho futuro |
| FINDINGS desatualizado (só oral/instância) | parcial | atualizar segunda com bloco cross-domain |
| NuInsSeg boundary | rodando | finalizar segunda |

---

## 3. O que JÁ está pronto (não refazer)

- ✅ Dados: 3 bases avaliadas pixel V1/V2 (oral, NuInsSeg full 665, IHC 266)
- ✅ Borda oral (com e sem função de perda) + NuInsSeg (rodando)
- ✅ 38 figuras geradas (selecionar, não recriar)
- ✅ Análise de saturação CellViT, tiling PathoSAM, ensemble, grid InstanSeg
- ✅ Diagnóstico de overlay (sem bug de implementação confirmado)
- ✅ Referências centrais + cadeia de argumento (FINDINGS §References)
