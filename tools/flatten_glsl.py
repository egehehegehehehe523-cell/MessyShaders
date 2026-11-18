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
    checks = [
        "shaders/world0/shadow.vsh",
        "shaders/world0/shadow.fsh",
        "shaders/world0/gbuffers_textured.vsh",
        "shaders/world0/gbuffers_terrain.vsh",
        "shaders/world0/gbuffers_entities.vsh",
        "shaders/world0/gbuffers_block.vsh",
        "shaders/world0/gbuffers_hand.vsh",
    ]
    for name in checks:
        text = flatten(name, files)
        match = re.match(r"#version\\s+(120|430 compatibility)", text)
        if not match:
            raise RuntimeError(f"Unexpected shader version in {name}")
        # Offline validator needs a high-enough *compatibility* profile to
        # accept existing E-Lite attributes and the experimental GL4 images.
        # Do not modify the actual ZIP's GLSL version here.
        text = text[:match.start()] + (
            "#version 430 compatibility\\n#define IS_IRIS 1\\n"
            "#define MC_VERSION 12101"
        ) + text[match.end():]
        stage = "vert" if name.endswith(".vsh") else "frag"
        ident = Path(name).stem.replace("gbuffers_", "")
        dest = args.output / f"world0_{ident}.{stage}"
        dest.write_text(text, encoding="utf-8")
        print(f"{name} -> {dest}")


if __name__ == "__main__":
    main()
