# Lâmina da Aurora

Jogo de ação em Python: um cavaleiro caminha por uma estrada antiga ladeada de colunas gregas e
enfrenta monstros que vêm de frente. Projeto **original**, sem relação com a Konami: não contém
código, arte nem música do Knightmare.

## Versões

| Arquivo | O que é |
|---|---|
| `lamina3d.py` | **3D (Panda3D)**: cena com sombras, névoa, colunas modeladas por código, personagens com animação de captura de movimento do Mixamo. Versão principal. |
| `lamina_aurora.py` | 2D pseudo-3D (pygame), terceira pessoa, sprites gerados por IA. |
| `lamina_aurora_v2_primeira_pessoa.py` | 2D pseudo-3D (pygame), primeira pessoa. |

## Instalação

Python 3.10+.

```
pip install -r requirements.txt
```

## Executar

```
python lamina3d.py          # versão 3D
python lamina_aurora.py     # versão 2D
```

### Controles (3D)

| Tecla | Ação |
|---|---|
| ↑ ↓ ← → ou W A S D | andar em qualquer direção |
| Espaço ou clique | atacar: soco (sem arma) ou salto com espada |
| Q ou Tab | trocar entre espada e punhos (depois de pegar a espada na estrada) |
| Esc | sair |

### Ciclo do dia

A partida começa ao meio-dia e escurece até a noite em 5 minutos (pôr do sol por volta dos
4 minutos). Para mudar a duração: `LAMINA_CICLO=600 python lamina3d.py` (segundos).

## Animações do Mixamo

As animações **não estão no repositório** (os termos da Adobe não permitem redistribuí-las soltas).
Baixe de graça no [Mixamo](https://www.mixamo.com/#/?page=9):

1. Entre com uma conta Adobe (gratuita).
2. Envie o cavaleiro (`mixamo/cavaleiro_para_mixamo.zip`, em **Upload Character**) e baixe com ele:
   - `Unarmed Walk Forward` → `heroi_andar.glb`
   - `Great Sword Jump Attack` → `heroi_espada.glb` (ataque com espada)
   - `Body Jab Cross` → `heroi_soco.glb` (ataque sem arma)

   Para os inimigos, com o personagem padrão do Mixamo:
   - `Standard Walk` → `andar.glb`
   - `Great Sword Slash` → `golpe.glb`
3. Baixe em **FBX Binary**, **With Skin**, 30 fps, e salve em `mixamo/baixados/`.
4. Converta para GLB com o [FBX2glTF](https://github.com/godotengine/FBX2glTF/releases) e
   prepare o arquivo para o Panda3D:

```
FBX2glTF --binary --input "mixamo/baixados/Standard Walk.fbx" --output mixamo/baixados/andar_bruto
python ferramentas/limpa_glb.py mixamo/baixados/andar_bruto.glb mixamo/baixados/andar.glb

FBX2glTF --binary --input "mixamo/baixados/Great Sword Slash.fbx" --output mixamo/baixados/golpe_bruto
python ferramentas/limpa_glb.py mixamo/baixados/golpe_bruto.glb mixamo/baixados/golpe.glb
```

(o mesmo para as três do herói). O `limpa_glb.py` reduz os pesos a 4 ossos por vértice: o Mixamo
exporta até 8 e o leitor do Panda3D perde o excesso (a malha fica parada).

Sem esses arquivos o jogo 3D roda com o cavaleiro de pernas articuladas por código e monstros 2D.


## Música

Coloque arquivos `.mp3`, `.ogg` ou `.wav` em `musica/`: tocam no lugar da música sintetizada
(versão 2D), um por fase.

## Estrutura

```
lamina3d.py            jogo 3D (Panda3D + simplepbr)
boneco3d.py            articula um modelo 3D sem esqueleto (quadril e joelho)
colunas3d.py           colunas clássicas procedurais (inteiras e quebradas)
lamina_aurora.py       jogo 2D (pygame)
arte/                  sprites e texturas
modelos/               modelos 3D (GLB)
ferramentas/           preparo de arte, estrada, animação e GLB
mixamo/                arquivos para enviar/baixar do Mixamo
musica/                músicas opcionais
```

## Créditos

- Arte e modelos 3D gerados por IA (Higgsfield) a partir de referências do autor.
- Animações de captura de movimento: [Mixamo](https://www.mixamo.com/#/?page=9) (Adobe), baixadas por quem joga.
- Efeitos sonoros e música sintetizados por código.
