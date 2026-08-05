"""IC/IR 因子筛查：通过 yq CLI 驱动的可复用脚本。

功能：
1. ``yq factor list --verbose``：列出全部注册因子与介绍（docstring 首行）
2. 单一因子：``yq factor run`` 计算因子值 → ``yq factor evaluate`` 展示
   该因子 1/5/20 日窗口的 IC 均值、IC_IR、分层多空收益
3. 多因子批量：多个因子拼成一张 factors parquet → ``yq factor evaluate``
   输出批量比较表（每因子一行，直接对比 IC_IR / 多空收益）

数据：
- 默认生成合成行情（30 股 × 250 交易日，收益 = beta*s_i + 噪声，s_i 为每股隐藏
  alpha），写入 ``data/audit/``，可复现（--seed）。注意：只要未来收益含截面
  alpha，凡从价格派生、能捕捉历史动量的因子（动量/OBV/RSI）IC 都会显著为正，
  这是合成数据强动量结构的自然结果；纯量因子（volume_ratio）IC≈0、波动率
  （calc_hv）轻微负 IC，形成对照。真实行情 IC 绝对值通常 0.02-0.10 即为有效
  因子，合成 IC 偏大属正常
- 传 ``--data path.parquet`` 使用真实行情（需含 date/code/close 等列）

用法：
    python notebooks/icir_factor_screening.py
    python notebooks/icir_factor_screening.py --data data/clean/ohlcv.parquet
    python notebooks/icir_factor_screening.py --factor calc_hv --factor calc_obv
    python notebooks/icir_factor_screening.py --n-stocks 50 --n-days 500 --seed 7
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = PROJECT_ROOT / "data" / "audit"
FACTOR_DIR = AUDIT_DIR / "icir_factors"

# 默认演示因子：动量 + 反转 + 波动 + 量价。合成数据强动量下，价格派生因子
# （动量/RSI/OBV）IC 显著为正，volume_ratio（纯量）≈0，calc_hv 轻微负，形成对照
DEFAULT_FACTORS = [
    "calc_momentum_5d_ratio",
    "calc_momentum_20d_return",
    "calc_rsi_6d",
    "calc_hv",
    "calc_obv",
    "calc_volume_ratio",
]
SINGLE_WINDOWS = ["1", "5", "20"]  # 单因子展示多窗口衰减
BATCH_WINDOWS = ["5"]  # 批量比较表固定 5 日窗口，每因子一行


def run_yq(args: list[str]) -> None:
    """调用 ``python -m yq``（subprocess），回显输出，失败即退出。"""
    cmd = [sys.executable, "-m", "yq", *args]
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(f"yq 命令失败（exit {proc.returncode}）: {' '.join(cmd)}")


def make_synthetic_ohlcv(
    n_stocks: int = 30, n_days: int = 250, seed: int = 42, beta: float = 0.02
) -> pd.DataFrame:
    """合成行情：收益 = beta * s_i + 噪声，s_i 为每股隐藏因子。

    过去 N 日累计收益 ≈ N*beta*s_i，与未来收益（beta*s_i）截面正相关，
    所以凡能捕捉历史动量的价格派生因子（动量/OBV/RSI）IC 显著为正；
    纯量因子（volume_ratio）与收益无关，IC≈0；波动率因子轻微负 IC。
    注意：合成数据信噪比高，IC 数值偏大（0.5-0.9）属正常，真实行情
    通常 IC 绝对值 0.02-0.10 即为有效因子。
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    codes = [f"{600000 + i:06d}" for i in range(n_stocks)]
    hidden = rng.normal(0.0, 1.0, n_stocks)  # 每股隐藏 alpha

    rows = []
    for i, code in enumerate(codes):
        eps = rng.normal(0.0, 0.02, n_days)
        ret = beta * hidden[i] + eps
        close = 100.0 * np.exp(np.cumsum(ret))
        prev = np.concatenate([[close[0] / (1 + ret[0])], close[:-1]])
        open_ = prev * (1 + rng.normal(0.0, 0.002, n_days))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0.0, 0.004, n_days)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0.0, 0.004, n_days)))
        volume = rng.lognormal(11.0, 0.3, n_days).astype(np.int64)
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": code,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "limit_up": False,
                    "limit_down": False,
                    "is_suspended": False,
                }
            )
        )
    df = pd.concat(rows, ignore_index=True)
    return df[["date", "code", "open", "high", "low", "close", "volume",
               "limit_up", "limit_down", "is_suspended"]]


def prepare_price(args) -> Path:
    """返回行情 parquet 路径：--data 校验通过即用，否则生成合成数据。"""
    if args.data:
        path = Path(args.data)
        if not path.exists():
            raise SystemExit(f"--data 文件不存在: {path}")
        df = pd.read_parquet(path)
        required = {"date", "code", "close"}
        missing = required - set(df.columns)
        if missing:
            raise SystemExit(f"--data 缺少列: {sorted(missing)}")
        print(f"使用真实行情: {path}（{len(df)} 行）")
        return path

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    price_file = (
        AUDIT_DIR / f"synthetic_ohlcv_{args.n_stocks}_{args.n_days}_{args.seed}.parquet"
    )
    if price_file.exists():
        print(f"复用合成行情缓存: {price_file}（删掉可重新生成）")
        return price_file
    print(f"生成合成行情: {args.n_stocks} 股 × {args.n_days} 日（seed={args.seed}）")
    make_synthetic_ohlcv(args.n_stocks, args.n_days, args.seed).to_parquet(
        price_file, index=False
    )
    return price_file


def compute_factor_files(
    price: Path, factors: list[str], no_cache: bool
) -> dict[str, Path]:
    """逐个 run 因子到 FACTOR_DIR/*.parquet，返回 {因子名: 路径}。"""
    FACTOR_DIR.mkdir(parents=True, exist_ok=True)
    for old in FACTOR_DIR.glob("*.parquet"):  # 清掉上次产物，保证干净可复现
        old.unlink()
    out: dict[str, Path] = {}
    for name in factors:
        path = FACTOR_DIR / f"{name}.parquet"
        args = ["factor", "run", name, "--input", str(price), "--output", str(path)]
        if no_cache:
            args.append("--no-cache")
        run_yq(args)
        out[name] = path
    return out


def merge_factor_panel(files: dict[str, Path]) -> Path:
    """把各因子 parquet 按 (date, code) 对齐拼成一张 factors parquet。"""
    panel = None
    for name, path in files.items():
        df = pd.read_parquet(path)[["date", "code", name]]
        panel = df if panel is None else panel.merge(df, on=["date", "code"])
    out = FACTOR_DIR / "factors_panel.parquet"
    panel.to_parquet(out, index=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IC/IR 因子筛查：列出因子与介绍，展示单因子和多因子批量比较表"
    )
    parser.add_argument(
        "--data", help="真实行情 parquet（date/code/close...），缺省用合成数据"
    )
    parser.add_argument(
        "--factor", action="append", default=None,
        help="要评估的因子名，可重复；缺省用内置演示集",
    )
    parser.add_argument(
        "--n-stocks", type=int, default=30, help="合成数据股票数（默认 30）"
    )
    parser.add_argument(
        "--n-days", type=int, default=250, help="合成数据交易日数（默认 250）"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="合成数据随机种子（默认 42）"
    )
    parser.add_argument("--no-cache", action="store_true", help="禁用因子磁盘缓存")
    args = parser.parse_args()

    factors = args.factor or DEFAULT_FACTORS

    print("=" * 70)
    print("IC/IR 因子筛查（yq CLI 驱动）")
    print("=" * 70)

    # 1. 列出全部注册因子与介绍
    run_yq(["factor", "list", "--verbose"])

    # 2. 数据准备
    price = prepare_price(args)
    files = compute_factor_files(price, factors, args.no_cache)

    # 3. 单一因子：逐因子展示多窗口 IC/IR + 分层多空
    for name in factors:
        print("\n" + "=" * 70)
        print(f"单一因子评估: {name}")
        print("=" * 70)
        run_yq(
            ["factor", "evaluate", "--input", str(files[name]),
             "--price", str(price), "--factor", name]
            + [f"--window={w}" for w in SINGLE_WINDOWS]
        )

    # 4. 多因子批量比较表：拼面板后一次 evaluate
    print("\n" + "=" * 70)
    print(f"多因子批量比较（{len(factors)} 个因子，5 日窗口）")
    print("=" * 70)
    panel = merge_factor_panel(files)
    run_yq(
        ["factor", "evaluate", "--input", str(panel), "--price", str(price)]
        + [f"--factor={f}" for f in factors]
        + [f"--window={w}" for w in BATCH_WINDOWS]
    )

    print(f"\n中间产物: {FACTOR_DIR}  | 行情: {price}")


if __name__ == "__main__":
    main()
