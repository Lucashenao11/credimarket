"""Métricas de evaluación y curva de costos (compartidas por las etapas B, D y la selección).

Costos ficticios fijados en ml/criterio_seleccion.md: aprobar a quien incumplirá (FN) cuesta 3 (revisado desde 5);
rechazar a quien habría pagado (FP) cuesta 1.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, brier_score_loss, classification_report,
                             confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score)

COSTO_FN = 3.0  # revisado de 5 a 3 el 16-nov, antes de usar la prueba (ver criterio_seleccion.md §5)
COSTO_FP = 1.0
MALLA_UMBRALES = np.round(np.arange(0.01, 1.0, 0.01), 2)


def metricas(y, p, umbral: float) -> dict:
    """Métricas de la clase positiva (1 = incumplimiento) para probabilidades p y un umbral."""
    y = np.asarray(y)
    pred = (np.asarray(p) >= umbral).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, p)),
        "average_precision": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "tasa_rechazo": float(pred.mean()),
        "costo_por_solicitud": float((COSTO_FN * fn + COSTO_FP * fp) / len(y)),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "matriz_confusion": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def curva_costos(y, p) -> pd.DataFrame:
    """Costo esperado por solicitud para cada umbral de la malla 0,01..0,99."""
    y = np.asarray(y)
    p = np.asarray(p)
    filas = []
    for u in MALLA_UMBRALES:
        pred = p >= u
        fn = int(((~pred) & (y == 1)).sum())
        fp = int((pred & (y == 0)).sum())
        filas.append({"umbral": float(u), "fn": fn, "fp": fp,
                      "costo": (COSTO_FN * fn + COSTO_FP * fp) / len(y)})
    return pd.DataFrame(filas)


def figura_matriz(matriz, titulo: str, ruta: Path) -> None:
    m = np.asarray(matriz)
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    ax.imshow(m, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{m[i, j]:,}", ha="center", va="center",
                    color="white" if m[i, j] > m.max() / 2 else "black", fontsize=12)
    ax.set_xticks([0, 1], ["aprobar (0)", "rechazar (1)"])
    ax.set_yticks([0, 1], ["paga (0)", "incumple (1)"])
    ax.set_xlabel("Predicción")
    ax.set_ylabel("Real")
    ax.set_title(titulo, fontsize=9)
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)


def figura_costos(costos: pd.DataFrame, umbral: float, titulo: str, ruta: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    ax.plot(costos["umbral"], costos["costo"])
    ax.axvline(umbral, linestyle="--", color="gray")
    ax.set_xlabel("Umbral")
    ax.set_ylabel(f"Costo por solicitud (FN={COSTO_FN:g}, FP={COSTO_FP:g})")
    ax.set_title(titulo, fontsize=9)
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)


def reporte_clasificacion(y, p, *umbrales: float) -> str:
    partes = []
    for u in umbrales:
        pred = (np.asarray(p) >= u).astype(int)
        partes.append(f"Umbral {u:.2f}\n" + classification_report(
            y, pred, labels=[0, 1], target_names=["paga (0)", "incumple (1)"], digits=4, zero_division=0))
    return "\n".join(partes)
