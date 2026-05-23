from pathlib import Path

import pandas as pd


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    """将 DataFrame 保存为 parquet 文件。

    自动创建父目录。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_parquet(path: Path) -> pd.DataFrame:
    """从 parquet 文件加载 DataFrame。

    Raises
    ------
    FileNotFoundError
        文件不存在时抛出。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return pd.read_parquet(path)
