# Módulo de Distribuição P2P e Paralelismo (OpenMP / CUDA)

Implementa a arquitetura distribuída e paralela descrita na Seção 3.5 do artigo do projeto, preservando integralmente o contrato HTTP/NDJSON `schema_version: 3`, os avisos de qualidade (`com_ressalvas`) e a política de retenção estritamente em memória RAM.

## Componentes

- `native/color_omp.c`, `native/build_omp.py`, `native/omp_bridge.py`: Kernel nativo em C com paralelismo a nível de dados (`#pragma omp parallel for`) para conversão fundida `sRGB → XYZ → CIELAB (D65)` (com tabela LUT `sRGB` exata em `float64`) e distância perceptual `CIEDE2000` em lote. Compila automaticamente em Linux (`gcc`/`clang`) e Windows (`MSVC cl.exe` ou `MinGW-w64`), com fallback automático e transparente para NumPy/scikit-image caso não exista compilador C.
- `protocol.py` e `codec.py`: Protocolo binário P2P persistente sobre TCP (`TCP_NODELAY`), seguro contra diferenças de endianness, SO (Linux ↔ Windows) e versão de Python (ex.: Python 3.12 `.venv-cuda` ↔ Python 3.14), **sem uso de `pickle`**. O recorte RGB é comprimido sem perdas com `zlib` nível 1 e enviado **uma única vez** por nó; tensores `Lab` (`float32`) nunca trafegam na rede; máscaras booleanas usam `np.packbits` + `zlib` (~1 B vazia, ~1–4 KB preenchida).
- `node.py`: Daemon de nó trabalhador P2P independente (`bisenet`, `acne`, `vitiligo`, `barba` e/ou `color_match`), com encaminhamento P2P direto entre estágios (Estágio 2 → Estágio 3) e canal de assinatura de saída para atravessar firewalls locais abrindo apenas **1 porta** na máquina GPU.
- `orchestrator.py`: Contém `LocalParallelExecutor` (padrão sem configuração extra, executando `cielab`, `mascara`, `acne`, `vitiligo` e `barba` simultaneamente) e `DistributedExecutor` (orquestração P2P com cancelamento `MSG_CANCEL` na desconexão e fallback configurável `local` ou `degrade`).
- `metrics.py`: Instrumentação sem reexecução das redes que calcula `desempenho` em toda análise (tempo real paralelo/distribuído vs. soma sequencial equivalente, speedup global, speedup do bloco concorrente de visão, speedup C/OpenMP vs. NumPy, nós ativos e bytes compactados na rede P2P).
- `cluster.py`: Inicializador multiplataforma PoC que lança os estágios como processos SO independentes na máquina principal, particiona automaticamente os threads CPU (`OMP_NUM_THREADS` / `MAQUIAGEM_ORT_THREADS`) e integra opcionalmente o nó NVIDIA GPU remoto.

---

## Como Executar o PoC

### 1. Modo Padrão (Processo Único com DAG Paralelo + OpenMP)

Nenhuma configuração extra é necessária; `python -m backend.app` já usa `LocalParallelExecutor` e compila/carrega o kernel OpenMP automaticamente se houver compilador C disponível.

Para compilar manualmente a biblioteca C/OpenMP:

```bash
# Linux / macOS
.venv/bin/python -m backend.src.distributed.native.build_omp --force

# Windows (PowerShell)
.venv\Scripts\python -m backend.src.distributed.native.build_omp --force
```

### 2. PoC Híbrido: Processos Locais + Nó NVIDIA GPU em Outra Máquina

**Na máquina com GPU NVIDIA** (ex.: Windows ou Linux com `.venv-cuda` conforme `docs/CUDA_SETUP.md`):

```powershell
# Windows (.venv-cuda) — abre apenas a porta TCP 7102 na máquina GPU
.venv-cuda\Scripts\python -m backend.src.distributed.node --bind 0.0.0.0:7102 --capabilities segmentation
```

*(Em Linux com GPU, substitua `.venv-cuda\Scripts\python` por `.venv-cuda/bin/python`.)*

**Na máquina principal** (Linux ou Windows):

```bash
# Linux
.venv/bin/python -m backend.src.distributed.cluster --gpu-peer IP_DA_MAQUINA_GPU:7102

# Windows (PowerShell)
.venv\Scripts\python -m backend.src.distributed.cluster --gpu-peer IP_DA_MAQUINA_GPU:7102
```

Enquanto a máquina GPU executa as 4 redes neurais (`BiSeNet`, `Acne`, `Vitiligo`, `Barba`) em CUDA a partir de um único envio do recorte RGB, o processo local `color_match` converte o recorte para `CIELAB` via OpenMP em paralelo e recebe as máscaras compactadas diretamente via P2P.

### 3. PoC 100% em Uma Máquina (Múltiplos Processos SO via P2P)

```bash
# Pipeline de 3 estágios em processos separados (Gateway -> Segmentação -> Cor/Match)
.venv/bin/python -m backend.src.distributed.cluster --topology stages

# Especialistas fragmentados (isola o YOLOv8l-seg de barba em processo próprio)
.venv/bin/python -m backend.src.distributed.cluster --topology sharded
```

Consulte o estado em tempo real dos nós P2P em `GET http://127.0.0.1:5000/api/cluster`.

### 4. Testes e Benchmarks

```bash
# Suite automatizada P2P, multi-processo, OpenMP e tolerância a falhas
.venv/bin/python -m unittest backend.tests.test_distributed -v

# Benchmark comparativo (mocks rápidos ou modelos ONNX reais)
.venv/bin/python -m backend.tests.bench_distributed
.venv/bin/python -m backend.tests.bench_distributed --real 5
```
