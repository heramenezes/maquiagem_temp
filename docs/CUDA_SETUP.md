# CUDA de Verdade — Como Ativar a GPU nos Especialistas

> **Situação atual (branch `paralelizar-mascaras`):**
> Os três detectores (acne, vitiligo, barba) já rodam **em paralelo** via
> `ThreadPoolExecutor`. O código em `runtime.py` já detecta e usa o
> `CUDAExecutionProvider` automaticamente — mas ele só entra em ação quando
> o pacote `onnxruntime-gpu` estiver instalado no ambiente.
>
> Hoje o ambiente padrão usa `onnxruntime` (CPU). As inferências acontecem
> na CPU mesmo que a GPU esteja disponível.

---

## Por que não está usando CUDA ainda

| O que falta | Motivo |
|---|---|
| `onnxruntime-gpu` não instalado | O venv atual tem `onnxruntime` (CPU-only) |
| Venv apontava para Python 3.11 | Python 3.11 foi desinstalado da máquina |
| `onnxruntime-gpu` exige Python ≤ 3.12 | Python 3.13/3.14 ainda não têm wheel GPU |

A GPU detectada é: **NVIDIA GeForce RTX 4060 — 8 GB VRAM — Driver 610.88 — CUDA 13.3**

---

## Passo a passo para ativar CUDA de verdade

### 1. Instalar Python 3.12

O `py` launcher já reconhece a versão. Verifique:

```powershell
py -0
```

Se `3.12` não aparecer na lista, baixe em https://www.python.org/downloads/release/python-3120/ e instale.

### 2. Criar o venv GPU

Na raiz do projeto:

```powershell
py -3.12 -m venv .venv-cuda
```

### 3. Instalar as dependências GPU

```powershell
.venv-cuda\Scripts\python -m pip install -r backend/requirements-cuda.txt
```

Isso instala `onnxruntime-gpu==1.21.0` no lugar do `onnxruntime` CPU-only.
O pacote já inclui as DLLs do CUDA necessárias — não é preciso instalar
o CUDA Toolkit separadamente para rodar o ONNX Runtime.

### 4. Baixar os modelos (se ainda não fez)

```powershell
.venv-cuda\Scripts\python -m backend.download_model
```

### 5. Rodar a aplicação

```powershell
.venv-cuda\Scripts\python -m backend.app
```

---

## Como confirmar que a GPU está sendo usada

Nos logs de inicialização do servidor, você verá:

```
INFO backend.src.skin_selection.runtime:
    ONNX Runtime: CUDAExecutionProvider disponível — usando GPU.
```

Se aparecer `indisponível — usando CPU`, o `onnxruntime-gpu` não foi
encontrado no ambiente ativo.

Você também pode verificar pelo benchmark:

```powershell
.venv-cuda\Scripts\python -m backend.tests.bench_pipeline --real 5
```

A coluna `provider` na tabela mostrará `CUDA` quando ativo.

---

## Como o código funciona

O arquivo [`backend/src/skin_selection/runtime.py`](runtime.py) tem a função:

```python
def _build_providers():
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        logger.info("ONNX Runtime: CUDAExecutionProvider disponível — usando GPU.")
        return [
            ("CUDAExecutionProvider", {"cudnn_conv_algo_search": "DEFAULT"}),
            "CPUExecutionProvider",   # fallback automático se a GPU falhar
        ]
    logger.info("ONNX Runtime: CUDAExecutionProvider indisponível — usando CPU.")
    return ["CPUExecutionProvider"]
```

Essa função é chamada **uma única vez por sessão ONNX**, no momento em que
o modelo é carregado na memória. Depois disso a sessão permanece em cache
(`_sessions`) e não é recriada.

O arquivo [`backend/src/skin_selection/pipeline.py`](pipeline.py) paraleliza
os três detectores:

```python
def select_skin(rgb, lab, anatomy):
    modules = {}
    with ThreadPoolExecutor(max_workers=len(DETECTORS)) as pool:
        futures = {pool.submit(run_module, key, rgb, anatomy): key for key in DETECTORS}
        for future in as_completed(futures):
            modules[futures[future]] = future.result()
    return finish(rgb, lab, anatomy, modules)
```

Com CUDA ativo, cada thread entrega o tensor para a GPU e aguarda o
resultado — o paralelismo de threads complementa o paralelismo da GPU.

---

## Resumo dos arquivos relevantes

| Arquivo | Papel |
|---|---|
| `backend/requirements.txt` | Ambiente padrão — CPU (`onnxruntime`) |
| `backend/requirements-cuda.txt` | Ambiente GPU (`onnxruntime-gpu`) |
| `backend/src/skin_selection/runtime.py` | Detecta GPU e cria sessões ONNX |
| `backend/src/skin_selection/pipeline.py` | Paraleliza os 3 detectores |
| `backend/tests/bench_pipeline.py` | Benchmark sequencial vs paralelo |
