# file: app/analytics/baseline.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def daily_frame(priced: pd.DataFrame, production: pd.DataFrame, weather: pd.DataFrame, tz: str = "UTC") -> pd.DataFrame:
    """One row per local day: kwh, cost, units_<product>, cooling/heating degree days, is_holiday, nonprod."""
    e = priced.assign(date=priced["ts"].dt.tz_convert(tz).dt.date).groupby("date").agg(
        kwh=("kwh", "sum"), cost=("cost", "sum"))
    prod = production.copy()
    prod["date"] = pd.to_datetime(prod["date"]).dt.date
    units = prod.pivot_table(index="date", columns="product", values="units", aggfunc="sum", fill_value=0)
    units.columns = [f"units_{c}" for c in units.columns]
    hol = prod.groupby("date")["is_holiday"].max().astype(bool).rename("is_holiday")
    w = weather.copy()
    w["date"] = pd.to_datetime(w["date"]).dt.date
    w = w.set_index("date")[["cooling_degree_days", "heating_degree_days"]]
    df = e.join(units, how="left").join(w, how="left").join(hol, how="left")
    ucols = list(units.columns)
    df[ucols] = df[ucols].fillna(0)
    df["is_holiday"] = df["is_holiday"].fillna(False).astype(bool)
    df[["cooling_degree_days", "heating_degree_days"]] = df[["cooling_degree_days", "heating_degree_days"]].fillna(0)
    df["nonprod"] = ((df[ucols].sum(axis=1) == 0) | df["is_holiday"]).astype(int)
    return df


def calendar_anomalies(production: pd.DataFrame) -> list[dict]:
    """Trap: a public holiday logged as a normal shift (or production on a flagged holiday)."""
    p = production.groupby("date").agg(units=("units", "sum"), is_holiday=("is_holiday", "max"),
                                       shift=("shift_pattern", "first")).reset_index()
    odd = p[(p["is_holiday"].astype(bool) & (p["units"] > 0)) |
            (~p["is_holiday"].astype(bool) & (p["units"] == 0) & ~p["shift"].astype(str).str.lower().isin(["none", "off", "0", ""]))]
    return [{"date": str(r.date), "units": int(r.units), "is_holiday": bool(r.is_holiday), "shift": r.shift}
            for r in odd.itertuples()]


@dataclass
class Baseline:
    coef: dict[str, float]
    features: list[str]
    r2: float
    cv_rmse: float
    n: int

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X = np.column_stack([np.ones(len(df))] + [df[f].to_numpy(float) for f in self.features])
        beta = np.array([self.coef["const"]] + [self.coef[f] for f in self.features])
        return X @ beta


def fit_baseline(daily: pd.DataFrame, features: list[str]) -> Baseline:
    feats = [f for f in features if f in daily and daily[f].astype(float).std() > 0]  # drop constant columns
    X = np.column_stack([np.ones(len(daily))] + [daily[f].to_numpy(float) for f in feats])
    y = daily["kwh"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    r2 = 1 - float(resid @ resid) / float(((y - y.mean()) ** 2).sum() or 1)
    cv = float(np.sqrt((resid ** 2).mean()) / (y.mean() or 1))
    coef = {"const": float(beta[0]), **{f: float(b) for f, b in zip(feats, beta[1:], strict=True)}}
    coef.update({f: 0.0 for f in features if f not in coef})
    return Baseline(coef=coef, features=features, r2=round(r2, 4), cv_rmse=round(cv, 4), n=len(daily))
