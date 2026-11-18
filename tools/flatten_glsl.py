#!/usr/bin/env python3
"""Flatten shaderpack #include directives for offline GLSL smoke compilation.

This is NOT the same as Iris' shaderpack preprocessing; runtime feature macros,
uniform mapping and Voxy interaction still require an in-game test.
"""
import argparse
from pathlib import Path
import re
from zipfile import ZipFile

INCLUDE = re.compile(r'^\s*#include\s+"(/[^"]+)"\s*$', flags=re.MULTILINE)


def flatten(name: str, files: dict[str, bytes], stack=()) -> str:
    if name in stack:
        raise RuntimeError(f"cyclic shader include: {stack + (name,)}")
    if name not in files:
        raise FileNotFoundError(name)
    text = files[name].decode("utf-8-sig", "replace")
    def include(match):
        child = "shaders" + match.group(1)
        return "\n// begin " + child + "\n" + flatten(child, files, stack + (name,)) + "\n// end " + child + "\n"
    return INCLUDE.sub(include, text)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archive", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    with ZipFile(args.archive) as z:
        files = {n: z.read(n) for n in z.namelist() if n.startswith("shaders/") and not n.endswith("/")}
    args.output.mkdir(parents=True, exist_ok=True)
    # Include gbuffers passes as well as the compute/shadow stages. The
    # normalizeLuma error happened in textured.vsh, which the old CI missed.
    # Every shipped G-buffer vertex/fragment wrapper, in every dimension,
    # plus shadow passes. Iris may rename the water pass to terrain_translucent
    # on some pipelines; the underlying include is shared.
    valid_roots = ("shaders/", "shaders/world0/", "shaders/world-1/", "shaders/world1/")
    checks = sorted(
        n for n in files
        if n.endswith((".vsh", ".fsh"))
        and n.rsplit("/", 1)[0] + "/" in valid_roots
        and (n.rsplit("/", 1)[1].startswith("gbuffers_")
             or n.rsplit("/", 1)[1].startswith("shadow."))
    )
    if not any("gbuffers_water.vsh" in n for n in checks):
        raise RuntimeError("Water/translucent vertex shader was not included in compile list")
    for name in checks:
        text = flatten(name, files)
        match = re.match(r"#version\s+(120|430 compatibility)", text)
        if not match:
            raise RuntimeError(f"Unexpected shader version in {name}")
        # Offline validator needs a high-enough *compatibility* profile to
        # accept existing E-Lite attributes and the experimental GL4 images.
        # Do not modify the actual ZIP's GLSL version here.
        text = text[:match.start()] + (
            "#version 430 compatibility\n#define IS_IRIS 1\n"
            "#define MC_VERSION 12101"
        ) + text[match.end():]
        stage = "vert" if name.endswith(".vsh") else "frag"
        ident = name.replace("/", "__").replace(".vsh", "").replace(".fsh", "")
        dest = args.output / f"{ident}.{stage}"
        dest.write_text(text, encoding="utf-8")
        print(f"{name} -> {dest}")


if __name__ == "__main__":
    main()
