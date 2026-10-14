"""
Backend - Sistema de Análise de Tons de Pele e Recomendação de Base (Escala Monk)
"""

from .preprocessing import (
    detectar_e_isolar_rosto,
    isolar_rosto_anatomico,
)

__all__ = [
    "detectar_e_isolar_rosto",
    "isolar_rosto_anatomico",
]
