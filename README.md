# Sistema de Análise de Tons de Pele e Recomendação de Base (Escala Monk)

Projeto backend para análise automatizada de tons de pele através de visão computacional e recomendação de bases cosméticas compatíveis com a **Monk Skin Tone Scale**, preparado para arquitetura distribuída (P2P) e aceleração paralela (CUDA/OpenMP).

---

## Estrutura do Repositório

O projeto foi estruturado em módulos independentes para facilitar a integração das próximas etapas do pipeline e da interface gráfica:

```text
maquiagem_temp/
├── backend/
│   ├── src/
│   │   ├── preprocessing/       # Módulo atual: detecção facial e isolamento anatômico
│   │   │   ├── face_detector.py # Bounding box rápida (MediaPipe + Haar fallback)
│   │   │   └── face_segmenter.py# Isolamento do contorno do rosto (Face Mesh)
│   │   ├── segmentation/        # Próxima etapa: CIELAB + K-Means dinâmico
│   │   ├── tone_matching/       # Próxima etapa: ITA, Escala Monk e KNN de bases
│   │   └── distributed/         # Próxima etapa: nós P2P e aceleração CUDA/OpenMP
│   ├── tests/                   # Bateria de testes automatizados do backend
│   │   └── test_preprocessing.py
│   └── requirements.txt         # Dependências do backend (OpenCV, MediaPipe, NumPy)
├── frontend/                    # Reservado para a interface do usuário (UI)
├── docs/                        # Documentação técnica e guias de funcionamento
│   └── COMO_FUNCIONA.md
├── samples/                     # Imagens de exemplo para testes locais
└── README.md
```

---

## Instalação das Dependências

Recomenda-se criar um ambiente virtual Python (3.10 ou 3.11):

```bash
# Instalação dos requisitos
pip install -r backend/requirements.txt
```

---

## Como Usar o Módulo Atual (Detecção e Isolamento Facial)

### 1. Bounding Box Rápida (Recorte Retangular)
```bash
python backend/src/preprocessing/face_detector.py samples/imagem_teste.jpeg
```

### 2. Silhueta Anatômica (Remove 100% do fundo e roupas)
```bash
python backend/src/preprocessing/face_segmenter.py samples/imagem_teste.jpeg samples/silhueta.png
```

### 3. Rodar os Testes Automatizados
```bash
python backend/tests/test_preprocessing.py
```

### 4. Uso via Código Python
```python
from backend.src.preprocessing import detectar_e_isolar_rosto, isolar_rosto_anatomico

# Bounding box pronta em RGB para o CIELAB
rosto_box = detectar_e_isolar_rosto("samples/imagem_teste.jpeg", retornar_rgb=True)

# Ou silhueta do contorno anatômico
rosto_silhueta = isolar_rosto_anatomico("samples/imagem_teste.jpeg", retornar_rgb=True)
```

---

## Próximos Módulos Planejados

1. **`backend/src/segmentation/`**: Conversão RGB $\rightarrow$ CIELAB, K-Means dinâmico e exclusão de áreas com condições pigmentares (acne, rosácea, vitiligo).
2. **`backend/src/tone_matching/`**: Cálculo do ITA (*Individual Typology Angle*), mapeamento para os 10 tons da Escala Monk e KNN para recomendar produtos da base de dados.
3. **`backend/src/distributed/`**: Troca de mensagens entre nós descentralizados P2P e kernels paralelos (OpenMP / CUDA).
4. **`frontend/`**: Integração com a interface visual de captura e recomendação.
