"""Parser for SPICE rawfiles (binary and ASCII) as written by ``ngspice -b -r``."""

from __future__ import annotations

from typing import Any

import numpy as np

from circuitos.simulation.results import Plot, Vector, canonical_name, kind_for, unit_for


def _read_line(buf: bytes, pos: int) -> tuple[str, int]:
    end = buf.index(b"\n", pos)
    return buf[pos:end].decode("latin-1").rstrip("\r"), end + 1


def parse_rawfile(buf: bytes) -> list[Plot]:
    plots: list[Plot] = []
    counters: dict[str, int] = {}
    pos = 0
    while pos < len(buf):
        header: dict[str, str] = {}
        variables: list[tuple[str, str]] = []
        while True:
            if pos >= len(buf):
                return plots
            line, pos = _read_line(buf, pos)
            if not line.strip():
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            if key == "variables":
                nvars = int(header["no. variables"])
                for _ in range(nvars):
                    vline, pos = _read_line(buf, pos)
                    parts = vline.split()
                    variables.append((parts[1], parts[2]))
                continue
            if key in ("binary", "values"):
                break
            header[key] = value.strip()
        npoints = int(header["no. points"].split()[0])
        is_complex = "complex" in header.get("flags", "").lower()
        nvars = len(variables)
        if key == "binary":
            width = 2 if is_complex else 1
            count = npoints * nvars * width
            flat = np.frombuffer(buf, dtype="<f8", count=count, offset=pos)
            pos += count * 8
            arr = flat.reshape(npoints, nvars, width)
            data: np.ndarray[Any, Any] = (
                arr[..., 0] + 1j * arr[..., 1] if is_complex else arr[..., 0]
            )
        else:
            data = np.zeros((npoints, nvars), dtype=complex if is_complex else float)
            for point in range(npoints):
                for var in range(nvars):
                    line, pos = _read_line(buf, pos)
                    while not line.strip():
                        line, pos = _read_line(buf, pos)
                    token = line.split()[-1]
                    if is_complex:
                        re_, im = token.split(",")
                        data[point, var] = complex(float(re_), float(im))
                    else:
                        data[point, var] = float(token)
        plot_name = header.get("plotname", "plot")
        kind = kind_for(plot_name)
        scale = canonical_name(*variables[0]) if variables and kind != "op" else None
        counters[kind] = counters.get(kind, 0) + 1
        # Same naming as the shared-library backend ("tran1", "ac1"...).
        name_out = f"{kind if kind != 'other' else 'plot'}{counters[kind]}"
        plot = Plot(name=name_out, kind=kind, scale=scale, title=plot_name)
        for index, (name, type_name) in enumerate(variables):
            column = data[:, index]
            if is_complex and index == 0 and type_name.lower() == "frequency":
                column = column.real  # the scale of an AC plot is real by definition
            cname = canonical_name(name, type_name)
            plot.vectors[cname] = Vector(cname, unit_for(type_name, name), column.copy())
        plots.append(plot)
    return plots
