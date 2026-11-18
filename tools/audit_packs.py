#!/usr/bin/env python3
"""Inspect exact shader archives and make an unmodified E-Lite comparison baseline.

This does not combine or distribute Complementary or Luxium shader code.
Results describe source structure, NOT actual FPS or GPU performance.
"""
from collections import Counter
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "makeup": "MakeUp-UltraFast-9.6.zip",
    "elite": "\u00a7lE-LITE shaders 5.1.3.zip",
    "complementary": "ComplementaryReimagined_r5.10.zip",
    "luxium": "Luxium-decompiled-2.8.4-pre-alpha.zip",
}
PATTERNS = {
    "dynamic_lighting": r"dynamic.?colored.?light|DYNAMIC_LIGHT|DCL_|dynamicLight",
    "rgb_lighting": r"COLORED_LIGHT|colored.?light|CANDLE_COLOR|COLORED_SHADOW",
    "voxel_propagation": r"floodfill|voxel.?light|image3D|sampler3D",
    "blocklight": r"blocklight|CANDLE_BASELIGHT|BLOCKLIGHT_TEMP",
    "shadow": r"shadowtex|shadow2D|SHADOW_CASTING",
    "pbr": r"LabPBR|IntegratedPBR|IPBR",
    "voxy": r"voxy|vxDepthTex",
}


def safe(name):
    name = name.replace("\\", "/")
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("Unsafe ZIP path: " + name)
    return p.as_posix()


def shader_prefix(names):
    candidates = [n[:-len("shaders/shaders.properties")] for n in names
                  if n.endswith("shaders/shaders.properties")]
    if not candidates:
        raise ValueError("shaders/shaders.properties not found")
    return min(candidates, key=len)


def audit(name, file):
    with ZipFile(file) as z:
        entries = [(safe(x.filename), x) for x in z.infolist() if not x.is_dir()]
        report = {
            "archive": file.name,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            "files": len(entries),
            "uncompressed_bytes": sum(x.file_size for _, x in entries),
            "types": dict(Counter(Path(n).suffix.lower() for n, _ in entries)),
        }
        if name == "luxium":
            report["relevant_paths"] = [n for n, _ in entries
                if any(x in n.lower() for x in
                       ("gpulocallightresolver", "gpushadowcache", "lightatlas",
                        "kawase", "neoshadows", "noiris"))][:50]
            return report
        prefix = shader_prefix([n for n, _ in entries])
        report["shader_root"] = prefix
        report["patterns"] = {}
        patterns = {k: re.compile(p, re.I) for k, p in PATTERNS.items()}
        totals = {k: [] for k in patterns}
        for n, x in entries:
            if not n.startswith(prefix + "shaders/") or not n.endswith((".glsl", ".fsh", ".vsh", ".properties")):
                continue
            if x.file_size > 3000000:
                continue
            body = z.read(x).decode("utf-8", "replace")
            for key, regex in patterns.items():
                hits = len(regex.findall(body))
                if hits:
                    totals[key].append({"path": n[len(prefix):], "hits": hits})
        for key, matches in totals.items():
            matches.sort(key=lambda x: -x["hits"])
            report["patterns"][key] = {
                "files": len(matches), "examples": matches[:20]
            }
        return report


def baseline(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as z:
        entries = [(safe(x.filename), x) for x in z.infolist() if not x.is_dir()]
        prefix = shader_prefix([n for n, _ in entries])
        payload = {n[len(prefix):]: z.read(x) for n, x in entries
                   if n.startswith(prefix) and n[len(prefix):]}
    assert "shaders/shaders.properties" in payload
    payload["MESSYSHADERS_BASELINE.txt"] = (
        "Unmodified source comparison baseline; NOT a completed hybrid shader.\n"
        "E-Lite 5.1.3 by Entokito: https://github.com/EntokitoDezonze/E-LITE-shaders\n"
        "Derived from MakeUp Ultra Fast: https://github.com/javiergcim/MakeUpUltraFast\n"
        "LGPL-3.0 license and original authorship apply. No Complementary, Luxium or Euphoria code included.\n"
    ).encode()
    with ZipFile(dest, "w", ZIP_DEFLATED, compresslevel=9) as out:
        for name, data in sorted(payload.items()):
            meta = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            meta.external_attr = 0o644 << 16
            meta.compress_type = ZIP_DEFLATED
            out.writestr(meta, data)
    with ZipFile(dest) as check:
        assert check.testzip() is None
        assert "shaders/shaders.properties" in check.namelist()
    return {"path": str(dest.relative_to(ROOT)),
            "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            "files": len(payload), "note": "No shader performance improvement claimed"}


def main():
    report = {"status": "static inspection only; no GPU measurements", "archives": {}}
    for name, file in FILES.items():
        print("Inspecting", file, flush=True)
        report["archives"][name] = audit(name, ROOT / file)
    report["baseline"] = baseline(ROOT / FILES["elite"], ROOT / "dist/MessyShaders-E-Lite-baseline.zip")
    (ROOT / "dist/audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    for name, info in report["archives"].items():
        print(name, info["files"], "files; uncompressed", info["uncompressed_bytes"], "bytes")
        for pat, data in info.get("patterns", {}).items():
            print(" ", pat, "in", data["files"], "files; top:", ", ".join(
                x["path"] for x in data["examples"][:4]))
        for path in info.get("relevant_paths", [])[:10]:
            print(" ", path)
    print("Baseline:", report["baseline"])
    print("Static matches are not a benchmark; no FPS claims.")


if __name__ == "__main__":
    main()
