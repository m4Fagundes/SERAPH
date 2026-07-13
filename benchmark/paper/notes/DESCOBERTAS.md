# Anotações das Métricas e Resultados

## Configuração

* Comparação entre **Cellpose**, **CellViT-SAM** e **PathoSAM** para segmentação de núcleos.
* Foram avaliadas 50 ROIs da classe severe que possuem ground truth.
* Métrica principal considerada: **F1-score**.

---

## Resultado Geral

| Modelo      | F1       |
| ----------- | -------- |
| Cellpose    | **0,70** |
| CellViT-SAM | 0,62     |
| PathoSAM    | 0,58     |

### Observação

O Cellpose apresentou o melhor resultado geral. A principal vantagem dele foi ter menos falsos positivos.

---

## Tabela Completa de Métricas (severe, 50 ROIs, IoU 0,5)

### Detecção (todas as instâncias)

| Modelo      | Precision | Recall   | F1       | F1 (micro) |
| ----------- | --------- | -------- | -------- | ---------- |
| Cellpose    | **0,79**  | 0,68     | **0,70** | **0,73**   |
| CellViT-SAM | 0,55      | **0,73** | 0,62     | 0,64       |
| PathoSAM    | 0,51      | 0,70     | 0,58     | 0,61       |

### Contorno e borda (só nos núcleos casados / TP)

| Modelo      | IoU      | Dice     | Boundary Recall | Boundary Precision | Boundary F | ASD      |
| ----------- | -------- | -------- | --------------- | ------------------ | ---------- | -------- |
| Cellpose    | **0,76** | **0,86** | 0,53            | **0,61**           | 0,55       | 1,98     |
| CellViT-SAM | 0,75     | 0,85     | **0,61**        | 0,56               | **0,58**   | **1,93** |
| PathoSAM    | 0,74     | 0,85     | 0,56            | 0,53               | 0,53       | 1,97     |

Notas:

* Em **negrito** o melhor de cada coluna.
* IoU, Dice e ASD são calculados só nos núcleos casados (TP); detecção é sobre todas as instâncias.
* ASD é distância de borda (px) — quanto **menor**, melhor.
* Cellpose domina a detecção (F1) e a Boundary Precision. CellViT lidera Recall, Boundary Recall e Boundary F. Dice praticamente empatado.

---

## Qualidade dos Contornos

Apesar da diferença no F1, os três métodos tiveram resultados muito parecidos em IoU, Dice e métricas de borda.

### Conclusão

Os modelos desenham os núcleos de forma semelhante. A maior diferença está em quantos núcleos cada um detecta.

---

## Boundary Recall e Dice

Avaliei também a Boundary Recall (BR) e o Dice médio.

| Modelo      | Dice | Boundary Recall | Boundary Precision | Boundary F |
| ----------- | ---- | --------------- | ------------------ | ---------- |
| CellViT-SAM | 0,85 | **0,61**        | 0,56               | **0,58**   |
| Cellpose    | 0,86 | 0,53            | **0,61**           | 0,55       |
| PathoSAM    | 0,85 | 0,56            | 0,53               | 0,53       |

### Observação

O Dice ficou empatado (~0,85). Mas na Boundary Recall e na Boundary F o CellViT foi o melhor — foi a primeira métrica onde ele ganhou do Cellpose. O Cellpose ganhou na Boundary Precision.

Detalhe que preciso lembrar: a Boundary Recall premia quem detecta mais. Como o CellViT detecta mais núcleos, ele cobre mais borda do GT. Então essa vantagem vem mais da quantidade de detecções do que de um contorno melhor por núcleo (o Dice, que é por núcleo, está empatado). Por isso anotei BR junto com Precision e F — sozinha ela engana.

### Conclusão

O ranking muda conforme a métrica. Cellpose ganha no F1 e na Boundary Precision. CellViT ganha na Boundary Recall e Boundary F. Não existe um vencedor único.

---

## Quem desenha melhor nos núcleos que todos acharam?

Peguei só os núcleos que os **3 modelos detectaram** (820 núcleos, 58% do GT) e comparei o contorno de cada um contra o GT. Assim a diferença de detecção não atrapalha a comparação.

| Modelo      | IoU      | Dice     | Vezes que foi o melhor |
| ----------- | -------- | -------- | ---------------------- |
| CellViT-SAM | **0,78** | **0,87** | **45%**                |
| PathoSAM    | 0,77     | 0,86     | 28%                    |
| Cellpose    | 0,76     | 0,86     | 26%                    |

### Conclusão

Quando todos acham o mesmo núcleo, o **CellViT desenha o contorno um pouco melhor** (e foi o melhor em quase metade dos casos). No geral o Dice parecia empatado porque a diferença de detecção escondia isso. Esse resultado bate com o que eu via na ferramenta.

---

## Por que CellViT e PathoSAM tiveram F1 menor?

Os dois métodos detectaram mais núcleos do que existem no ground truth.

* Cellpose: ~25 núcleos por ROI
* CellViT: ~39 núcleos por ROI
* PathoSAM: ~39 núcleos por ROI
* Ground truth: ~28 núcleos por ROI

### Conclusão

O problema principal não parece ser a segmentação em si, mas o excesso de detecções, aumentando a quantidade de falsos positivos.

---

## Fragmentação de Núcleos

Foi investigada a hipótese de que alguns modelos dividem um núcleo em várias partes.

### Resultado

* Cellpose: praticamente não fragmenta.
* CellViT: cerca de 7%.
* PathoSAM: cerca de 8%.

### Conclusão

A fragmentação existe, mas não é o principal problema. O efeito mais importante é que alguns núcleos ficam menores do que o esperado ou aparecem em regiões sem anotação.

---

## Possível Problema do Ground Truth

Durante a inspeção visual foi observado que:

* Alguns núcleos detectados por CellViT e PathoSAM não possuem anotação no ground truth.
* Em vários casos as máscaras previstas ficam ligeiramente menores que as máscaras anotadas.

### Conclusão

Parte da diferença entre os modelos pode estar relacionada ao próprio conjunto de anotações e não necessariamente a erros dos modelos.

Ainda precisa ser investigado com mais cuidado.

---

## Comparação Sem Ground Truth

Foi feito um teste em uma imagem sem anotação.

Quantidade de núcleos detectados:

* Cellpose: 289
* CellViT: 318
* PathoSAM: 331

### Conclusão

Os três métodos produziram resultados bastante parecidos. Isso sugere que CellViT e PathoSAM não estão com configuração incorreta.

---

## Formato das Máscaras

Foi verificado se o uso de PNG poderia causar perda de informação.

### Conclusão

Não. PNG é um formato sem perdas e não afetou os resultados.

---

## Hiperparâmetros

Foi feita uma revisão da documentação e dos artigos dos modelos.

### Principais observações

* Os parâmetros atuais do Cellpose parecem adequados.
* A magnificação utilizada pelo CellViT está correta.
* O tiling do PathoSAM pode estar prejudicando os resultados em imagens pequenas.

---

## Teste do PathoSAM sem Tiling

Resultado do experimento:

* F1 passou de **0,61 para 0,64**.
* Houve redução de falsos positivos.
* Houve aumento de verdadeiros positivos.

### Conclusão

Desabilitar o tiling melhora o desempenho do PathoSAM. Mesmo assim, ele continua abaixo do Cellpose neste conjunto de dados.

---

## Resultado no Healthy (a outra metade dos dados)

Rodei a mesma avaliação nas 50 ROIs healthy.

| Modelo      | Precision | Recall   | F1       | Dice     |
| ----------- | --------- | -------- | -------- | -------- |
| Cellpose    | **0,86**  | 0,80     | **0,83** | 0,89     |
| CellViT-SAM | 0,50      | **0,83** | 0,61     | **0,89** |
| PathoSAM    | 0,49      | 0,80     | 0,60     | 0,89     |

### Severe x Healthy (F1)

| Modelo      | Severe   | Healthy  |
| ----------- | -------- | -------- |
| Cellpose    | 0,70     | **0,83** |
| CellViT-SAM | 0,62     | 0,61     |
| PathoSAM    | 0,58     | 0,60     |

### Observações

* O **ranking é o mesmo** nos dois tecidos: Cellpose > CellViT > PathoSAM. Resultado consistente.
* No healthy o **Cellpose melhora bastante** (F1 0,70 → 0,83), mas CellViT e PathoSAM quase não mudam. A vantagem do Cellpose aumenta no tecido saudável.
* CellViT e PathoSAM continuam detectando demais (~43 por ROI contra ~26 do GT), então a precisão deles segue baixa (~0,50).
* Nos núcleos que os 3 acharam, o CellViT ainda desenha um pouco melhor, mas a diferença é menor que no severe.

---

## Variação de Limiar (curva precisão × recall)

Rodei os 3 modelos variando o limiar de detecção de cada um (o knob é diferente em cada: Cellpose usa cellprob, CellViT e PathoSAM usam foreground 0–1).

Melhor F1 de cada modelo (no melhor limiar):

| Modelo      | Severe (melhor F1) | Healthy (melhor F1) |
| ----------- | ------------------ | ------------------- |
| Cellpose    | **0,745** (cellprob −0,5) | **0,830** (cellprob −0,5) |
| PathoSAM    | 0,647 (fg 0,4)     | 0,672 (fg 0,5)      |
| CellViT-SAM | 0,629 (fg 0,1)     | 0,612 (fg 0,7)      |

### Observações

* **O ranking não muda mexendo no limiar.** Mesmo no melhor ajuste de cada um, Cellpose > PathoSAM > CellViT, nos dois tecidos. Não dá pra ajustar o limiar pra fazer CellViT/PathoSAM ganharem do Cellpose neste GT.
* **Os modelos diferem na "tunabilidade":** o Cellpose tem um limiar que realmente troca precisão por recall (curva larga); o **CellViT é saturado** (o limiar quase não muda nada, curva plana); o PathoSAM tem faixa estreita.
* **O melhor limiar do Cellpose foi cellprob = −0,5 nos dois tecidos** (um pouco melhor que o default 0,0). Resultado reproduzível.

### Conclusão

A vantagem do Cellpose não é só do limiar padrão — ele se mantém na frente em qualquer limiar. E a impossibilidade de tunar o CellViT (saturação) é em si um ponto a destacar.

---

## Pontos Importantes para o Artigo

* Cellpose teve o melhor F1.
* A qualidade dos contornos (Dice) foi parecida entre os três métodos.
* O ranking muda conforme a métrica: Cellpose ganha no F1 e na Boundary Precision; CellViT ganha na Boundary Recall e Boundary F. Não tem vencedor único.
* As diferenças aparecem principalmente na etapa de detecção.
* Existe evidência de que o ground truth pode influenciar fortemente os resultados.
* Remover o tiling do PathoSAM trouxe melhora consistente.
* O ranking se manteve nas duas metades dos dados (severe e healthy), o que reforça a robustez do resultado.
* O ranking também se manteve variando o limiar de detecção: o Cellpose fica na frente em qualquer ajuste.
* O CellViT é saturado (não dá pra ajustar o limiar dele) — é um ponto a destacar.

---

## Próximos Passos

* Verificar se os núcleos sem anotação são erros dos modelos ou falhas do ground truth.
* Confirmar os resultados do PathoSAM em mais imagens.
* Fazer ajuste sistemático dos hiperparâmetros.
* Adicionar métricas como PQ e mAP.
* Comparar separadamente casos saudáveis e severe.



I = ALFA Cellpose + (1-ALPHA)Phatosan