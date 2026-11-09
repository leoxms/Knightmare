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
| Espaço ou clique | atacar na direção em que o cavaleiro olha |
| Esc | sair |

## Animações do Mixamo

As animações **não estão no repositório** (os termos da Adobe não permitem redistribuí-las soltas).
Baixe de graça no [Mixamo](https://www.mixamo.com/#/?page=9):

1. Entre com uma conta Adobe (gratuita).
2. Escolha o personagem e as animações. O jogo usa:
   - `Standard Walk` (herói e inimigos andando)
   - `Great Sword Slash` (golpe dos inimigos)
3. Baixe em **FBX Binary**, **With Skin**, 30 fps, e salve em `mixamo/baixados/`.
4. Converta para GLB com o [FBX2glTF](https://github.com/godotengine/FBX2glTF/releases) e
   prepare o arquivo para o Panda3D:

```
FBX2glTF --binary --input "mixamo/baixados/Standard Walk.fbx" --output mixamo/baixados/andar_bruto
python ferramentas/limpa_glb.py mixamo/baixados/andar_bruto.glb mixamo/baixados/andar.glb

FBX2glTF --binary --input "mixamo/baixados/Great Sword Slash.fbx" --output mixamo/baixados/golpe_bruto
python ferramentas/limpa_glb.py mixamo/baixados/golpe_bruto.glb mixamo/baixados/golpe.glb
```

Sem esses arquivos o jogo 3D roda com o cavaleiro de pernas articuladas por código e monstros 2D.

Para usar o cavaleiro do jogo no Mixamo, envie `mixamo/cavaleiro_para_mixamo.zip` em
**Upload Character**.

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
