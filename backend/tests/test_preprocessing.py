import os
import sys
import numpy as np

# Adiciona o diretorio backend ao sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.preprocessing import (
    carregar_imagem,
    detectar_e_isolar_rosto,
    isolar_rosto_anatomico,
)


def obter_imagem_teste() -> str:
    pasta_samples = os.path.abspath(os.path.join(backend_dir, "..", "samples"))
    for arq in os.listdir(pasta_samples):
        if arq.lower().endswith((".jpg", ".jpeg", ".png")) and "recorte" not in arq and "silhueta" not in arq:
            return os.path.join(pasta_samples, arq)
    raise FileNotFoundError("Nenhuma imagem de amostra encontrada na pasta samples/.")


def testar_deteccao_quadrada():
    print("\n--- Teste 1: Deteccao facial com bounding box ---")
    caminho = obter_imagem_teste()
    print(f"Usando imagem: {os.path.basename(caminho)}")

    rosto = detectar_e_isolar_rosto(caminho, retornar_rgb=True)
    assert rosto is not None, "Falha: rosto deveria ter sido detectado!"
    assert isinstance(rosto, np.ndarray), "O retorno deve ser numpy.ndarray!"
    assert rosto.flags["C_CONTIGUOUS"], "A matriz deve ser C-contigua para CUDA/OpenMP!"
    print(f"[PASSOU] Rosto recortado com sucesso: {rosto.shape[1]}x{rosto.shape[0]} px (RGB).")


def testar_isolamento_anatomico():
    print("\n--- Teste 2: Isolamento anatomico do contorno facial ---")
    caminho = obter_imagem_teste()
    silhueta = isolar_rosto_anatomico(caminho, retornar_rgb=True, fundo_transparente=False)
    assert silhueta is not None, "Falha: silhueta deveria ter sido extraida!"
    assert isinstance(silhueta, np.ndarray), "O retorno deve ser numpy.ndarray!"
    print(f"[PASSOU] Silhueta isolada com sucesso: {silhueta.shape[1]}x{silhueta.shape[0]} px.")


def testar_processamento_em_memoria():
    print("\n--- Teste 3: Processamento direto da memoria (padrao P2P) ---")
    caminho = obter_imagem_teste()
    img_array = carregar_imagem(caminho)

    rosto = detectar_e_isolar_rosto(img_array, retornar_rgb=True)
    assert rosto is not None, "Falha: deveria processar array diretamente em memoria!"
    print(f"[PASSOU] Array em memoria processado: {rosto.shape}.")


def testar_imagem_sem_rosto():
    print("\n--- Teste 4: Imagem preta (sem face) ---")
    img_vazia = np.zeros((300, 300, 3), dtype=np.uint8)
    assert detectar_e_isolar_rosto(img_vazia) is None
    assert isolar_rosto_anatomico(img_vazia) is None
    print("[PASSOU] Retornou None para imagem sem rosto.")


def testar_arquivo_inexistente():
    print("\n--- Teste 5: Tratamento de arquivo inexistente ---")
    try:
        detectar_e_isolar_rosto("caminho_inexistente_xyz.jpg")
        assert False, "Deveria ter lancado FileNotFoundError!"
    except FileNotFoundError:
        print("[PASSOU] FileNotFoundError lancado corretamente.")


if __name__ == "__main__":
    print("============================================================")
    print(" BATERIA DE TESTES DO BACKEND (PREPROCESSING)")
    print("============================================================")

    testar_deteccao_quadrada()
    testar_isolamento_anatomico()
    testar_processamento_em_memoria()
    testar_imagem_sem_rosto()
    testar_arquivo_inexistente()

    print("\n============================================================")
    print(" [TODOS OS TESTES PASSARAM COM SUCESSO!]")
    print("============================================================")
