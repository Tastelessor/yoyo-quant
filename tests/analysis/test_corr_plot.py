import matplotlib

matplotlib.use("Agg")

import pandas as pd

from analysis.plot import plot_cluster_dendrogram, plot_corr_matrix


def _corr_matrix():
    return pd.DataFrame(
        [
            [1.0, 0.95, 0.10],
            [0.95, 1.0, 0.05],
            [0.10, 0.05, 1.0],
        ],
        index=["a", "b", "c"],
        columns=["a", "b", "c"],
    )


def test_plot_corr_matrix_returns_figure_and_saves(tmp_path):
    fig = plot_corr_matrix(_corr_matrix(), title="test")
    assert fig is not None
    out = tmp_path / "corr.png"
    fig.savefig(out, dpi=72)
    assert out.exists() and out.stat().st_size > 0


def test_plot_corr_matrix_uses_red_yellow_green():
    fig = plot_corr_matrix(_corr_matrix())
    im = fig.axes[0].images[0]
    assert im.get_cmap().name == "RdYlGn"


def test_plot_dendrogram_returns_figure_and_saves(tmp_path):
    fig = plot_cluster_dendrogram(_corr_matrix(), threshold=0.7)
    assert fig is not None
    out = tmp_path / "dendro.png"
    fig.savefig(out, dpi=72)
    assert out.exists() and out.stat().st_size > 0


def test_plot_dendrogram_three_leaves():
    fig = plot_cluster_dendrogram(_corr_matrix())
    leaves = fig.axes[0].get_xticklabels()
    assert len(leaves) == 3
