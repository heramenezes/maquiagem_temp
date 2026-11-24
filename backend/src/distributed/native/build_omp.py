"""Compilação multiplataforma (Linux / Windows / macOS) do kernel C/OpenMP."""

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "color_omp.c"


def library_path() -> Path:
    system = platform.system().lower()
    if system == "windows":
        return HERE / "color_omp.dll"
    if system == "darwin":
        return HERE / "libcolor_omp.dylib"
    return HERE / "libcolor_omp.so"


def build_library(*, force: bool = False) -> Path | None:
    """Compila color_omp.c com OpenMP quando um compilador C estiver disponível.

    Retorna o caminho da biblioteca compartilhada ou None se não houver compilador.
    """
    target = library_path()
    if target.is_file() and not force:
        try:
            if target.stat().st_mtime_ns >= SOURCE.stat().st_mtime_ns:
                return target
        except OSError:
            pass

    system = platform.system().lower()
    candidates: list[list[str]] = []

    if system == "windows":
        if shutil.which("cl"):
            candidates.append(["cl", "/nologo", "/O2", "/openmp", "/LD", str(SOURCE), f"/Fe:{target}"])
        if shutil.which("gcc"):
            candidates.append(["gcc", "-O3", "-fopenmp", "-shared", str(SOURCE), "-o", str(target), "-lm"])
        if shutil.which("clang"):
            candidates.append(["clang", "-O3", "-fopenmp", "-shared", str(SOURCE), "-o", str(target), "-lm"])
    else:
        for cc in ("gcc", "cc", "clang"):
            if shutil.which(cc):
                # Tenta com OpenMP primeiro, depois sem OpenMP se libomp não estiver instalado.
                candidates.append([cc, "-O3", "-fopenmp", "-fPIC", "-shared", str(SOURCE), "-o", str(target), "-lm"])
                candidates.append([cc, "-O3", "-fPIC", "-shared", str(SOURCE), "-o", str(target), "-lm"])

    tmp_target = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    for cmd in candidates:
        actual_cmd = [
            f"/Fe:{tmp_target}" if arg.startswith("/Fe:") else (str(tmp_target) if arg == str(target) else arg)
            for arg in cmd
        ]
        try:
            proc = subprocess.run(
                actual_cmd,
                cwd=str(HERE),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode == 0 and tmp_target.is_file():
                os.replace(tmp_target, target)
                for ext in (".obj", ".exp", ".lib"):
                    artifact = tmp_target.with_suffix(ext)
                    if artifact.is_file():
                        artifact.unlink(missing_ok=True)
                return target
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            tmp_target.unlink(missing_ok=True)

    return target if target.is_file() else None


if __name__ == "__main__":
    built = build_library(force="--force" in sys.argv)
    if built is None:
        print("Nenhum compilador C compatível encontrado; usando fallback NumPy.", file=sys.stderr)
        sys.exit(1)
    print(f"Biblioteca nativa compilada em: {built}")
