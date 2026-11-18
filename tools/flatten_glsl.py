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
    checks = ["shaders/world0/shadow.vsh", "shaders/world0/shadow.fsh"]
    for name in checks:
        text = flatten(name, files)
        if not text.startswith("#version 430 compatibility"):
            raise RuntimeError(f"Not GLSL 430 compatibility: {name}")
        text = text.replace("#version 430 compatibility",
             "#version 430 compatibility\n#define IS_IRIS 1\n#define MC_VERSION 12101", 1)
        dest = args.output / ("world0_shadow." + ("vert" if name.endswith(".vsh") else "frag"))
        dest.write_text(text, encoding="utf-8")
        print(f"{name} -> {dest}")


if __name__ == "__main__":
    main()
